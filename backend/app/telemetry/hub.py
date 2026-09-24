"""
TelemetryHub: WebSocket connection manager. Lives in the API process only.

  run_id -> {clients}      An event for run A is never sent to a client of run B.
  notify_run(run_id)       "something was committed for this run": every client of that run fetches the events
                           after ITS OWN cursor from PostgreSQL and enqueues them (so live delivery, replay after a
                           reconnect and the initial snapshot share one code path and cannot produce gaps/duplicates).
  per-client bounded queue + sender task
                           A slow browser can only fill its own queue; on overflow (or a send timeout) that client is
                           dropped (close 1013) and recovers from the DB by reconnecting. Nothing here can block Kafka
                           processing: the Scheduler is a different process and never calls the hub.

Every public method swallows and logs its own errors: telemetry must never break anything else.
"""

import asyncio
import json
import logging
from typing import Any, Callable

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.core.metrics import metrics
from app.db.database import SessionLocal
from app.telemetry import store
from app.telemetry.contract import HEARTBEAT_S, QUEUE_MAX, SEND_TIMEOUT_S

logger = logging.getLogger(__name__)

SLOW_CONSUMER = 1013


class Client:
    def __init__(self, websocket: WebSocket, run_id: str, queue_size: int):
        self.websocket = websocket
        self.run_id = run_id
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_size)
        self.cursor: store.Cursor | None = None
        self.ready = False        # set once the snapshot was queued; live delivery is skipped before that
        self.closed = False
        self.lock = asyncio.Lock()  # serialises delivery for this client
        self.tasks: list[asyncio.Task] = []


class TelemetryHub:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        queue_size: int = QUEUE_MAX,
        send_timeout: float = SEND_TIMEOUT_S,
        heartbeat_s: float = HEARTBEAT_S,
    ) -> None:
        self.session_factory = session_factory
        self.queue_size = queue_size
        self.send_timeout = send_timeout
        self.heartbeat_s = heartbeat_s
        self._clients: dict[str, set[Client]] = {}
        self.dropped_slow = 0

    # ── subscriptions ───────────────────────────────────────────────────

    def subscribe(self, client: Client) -> None:
        self._clients.setdefault(client.run_id, set()).add(client)

    def unsubscribe(self, client: Client) -> None:
        clients = self._clients.get(client.run_id)
        if clients is not None:
            clients.discard(client)
            if not clients:
                del self._clients[client.run_id]

    def client_count(self, run_id: str | None = None) -> int:
        if run_id is not None:
            return len(self._clients.get(run_id, ()))
        return sum(len(c) for c in self._clients.values())

    def run_ids(self) -> list[str]:
        return list(self._clients)

    # ── connection lifecycle ────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, run_id: str, last_event_id: str | None = None) -> Client | None:
        """
        Register an ACCEPTED websocket for `run_id` and send the snapshot. Returns None (after closing with
        4404 / 1011) if the run does not exist or the snapshot failed. Never raises.
        """
        client = Client(websocket, run_id, self.queue_size)
        metrics.inc("websocket_connections")
        if last_event_id:
            metrics.inc("websocket_reconnects")  # a client resuming after a drop
        self.subscribe(client)  # subscribe first: nothing committed during the snapshot can be missed
        try:
            snapshot, cursor = await asyncio.to_thread(self._snapshot, run_id, last_event_id)
        except store.RunNotFound:
            self.unsubscribe(client)
            await self._close(websocket, 4404, "run not found")
            return None
        except Exception:
            logger.exception("Telemetry snapshot failed for run %s", run_id)
            self.unsubscribe(client)
            await self._close(websocket, 1011, "snapshot unavailable")
            return None

        client.cursor = cursor
        client.tasks = [asyncio.create_task(self._sender(client)), asyncio.create_task(self._heartbeat(client))]
        self._enqueue(client, snapshot)
        client.ready = True
        await self._deliver(client)  # anything committed while the snapshot was being built
        return client

    async def disconnect(self, client: Client) -> None:
        client.closed = True
        self.unsubscribe(client)
        for t in client.tasks:
            t.cancel()
        client.tasks = []

    async def close_all(self) -> None:
        for clients in list(self._clients.values()):
            for c in list(clients):
                await self._drop(c, 1001, "server shutting down")

    # ── delivery ────────────────────────────────────────────────────────

    def notify_run(self, run_id: str) -> None:
        """A commit happened for `run_id`: every client of that run catches up from the DB."""
        for client in list(self._clients.get(run_id, ())):
            if client.ready and not client.closed:
                asyncio.create_task(self._safe_deliver(client))

    def notify_all(self) -> None:
        for run_id in self.run_ids():
            self.notify_run(run_id)

    def broadcast_to_run(self, run_id: str, message: dict[str, Any]) -> int:
        """Enqueue an arbitrary message for every ready client of one run. Returns how many accepted it."""
        return sum(self._enqueue(c, message) for c in list(self._clients.get(run_id, ())) if c.ready and not c.closed)

    def broadcast(self, message: dict[str, Any]) -> int:
        """Enqueue a message for every ready client of every run (e.g. maintenance notices)."""
        return sum(self.broadcast_to_run(run_id, message) for run_id in self.run_ids())

    def send(self, client: Client, message: dict[str, Any]) -> bool:
        """Enqueue one message for one client (used for pong replies)."""
        return self._enqueue(client, message)

    async def _safe_deliver(self, client: Client) -> None:
        try:
            await self._deliver(client)
        except Exception:
            logger.exception("Telemetry delivery failed for run %s", client.run_id)

    async def _deliver(self, client: Client) -> None:
        async with client.lock:
            if client.closed or not client.ready:
                return
            messages, state, cursor = await asyncio.to_thread(self._updates, client.run_id, client.cursor)
            if not messages:
                return
            client.cursor = cursor
            for m in messages:
                if not self._enqueue(client, m):
                    return
            self._enqueue(client, {"type": "workflow.state", "run_id": client.run_id, "state": state})

    # ── per-client queue, sender, heartbeat ─────────────────────────────

    def _enqueue(self, client: Client, message: dict[str, Any]) -> bool:
        if client.closed:
            return False
        try:
            client.queue.put_nowait(json.dumps(message, default=str))
            return True
        except asyncio.QueueFull:
            # Backpressure: a slow browser must never hold anything up. Drop it; it recovers by reconnecting.
            self.dropped_slow += 1
            metrics.inc("websocket_slow_client_drops")
            logger.warning("Telemetry client for run %s is too slow (queue full): dropping it", client.run_id)
            asyncio.create_task(self._drop(client, SLOW_CONSUMER, "slow consumer"))
            return False

    async def _sender(self, client: Client) -> None:
        try:
            while True:
                frame = await client.queue.get()
                await asyncio.wait_for(client.websocket.send_text(frame), self.send_timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._drop(client, None, None)  # broken/stalled socket

    async def _heartbeat(self, client: Client) -> None:
        try:
            while True:
                await asyncio.sleep(self.heartbeat_s)
                if not client.queue.full():
                    self._enqueue(client, {"type": "heartbeat", "ts": _now_iso()})
        except asyncio.CancelledError:
            raise

    async def _drop(self, client: Client, code: int | None, reason: str | None) -> None:
        if client.closed:
            return
        await self.disconnect(client)
        if code is not None:
            await self._close(client.websocket, code, reason or "")

    @staticmethod
    async def _close(websocket: WebSocket, code: int, reason: str) -> None:
        try:
            await websocket.close(code=code, reason=reason)
        except Exception:
            pass  # already closed

    # ── sync DB helpers (run in a worker thread) ────────────────────────

    def _snapshot(self, run_id: str, last_event_id: str | None):
        with self.session_factory() as db:
            return store.build_snapshot(db, run_id, last_event_id)

    def _updates(self, run_id: str, cursor):
        with self.session_factory() as db:
            return store.fetch_updates(db, run_id, cursor)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
