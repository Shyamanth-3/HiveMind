"""
PostgreSQL LISTEN/NOTIFY bridge: Scheduler process -> API process.

The Scheduler commits an event, then (best effort, after the commit) runs `NOTIFY hivemind_events, '<run_id>'`.
This listener, running inside the FastAPI process, wakes the hub, which reads the committed rows. Because the
notification is only sent after commit, a browser can never see a state the database does not yet have.

Loss-tolerant on purpose: NOTIFY is fire-and-forget, so the listener also (a) catches every subscribed run up
whenever the LISTEN connection (re)connects and (b) does that every POLL_S seconds. Clients read the durable
event history by cursor, so a lost or late notification only delays an update.

It runs in a dedicated thread with a synchronous psycopg connection (psycopg's async mode cannot use the
ProactorEventLoop that uvicorn uses on Windows) and hands notifications to the event loop thread-safely.
"""

import asyncio
import logging
import threading

import psycopg
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.telemetry.contract import NOTIFY_CHANNEL, valid_id
from app.telemetry.hub import TelemetryHub

logger = logging.getLogger(__name__)

POLL_S = 5.0
MAX_BACKOFF_S = 30.0


def listen_dsn() -> str:
    return make_url(settings.DATABASE_URL).set(drivername="postgresql").render_as_string(hide_password=False)


class NotifyListener:
    def __init__(self, hub: TelemetryHub, loop: asyncio.AbstractEventLoop, dsn: str | None = None,
                 poll_s: float = POLL_S) -> None:
        self.hub, self.loop, self.dsn, self.poll_s = hub, loop, dsn or listen_dsn(), poll_s
        self.connected = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="telemetry-listener", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    # ── thread body ─────────────────────────────────────────────────────

    def _wake(self, run_id: str | None) -> None:
        """Ask the hub (event loop thread) to catch up. Never raises."""
        try:
            fn = self.hub.notify_all if run_id is None else (lambda: self.hub.notify_run(run_id))
            self.loop.call_soon_threadsafe(fn)
        except RuntimeError:
            pass  # loop closed: shutting down

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                with psycopg.connect(self.dsn, autocommit=True) as conn:
                    conn.execute(f"LISTEN {NOTIFY_CHANNEL}")
                    logger.info("Telemetry listener connected (channel %s)", NOTIFY_CHANNEL)
                    self.connected.set()
                    backoff = 1.0
                    self._wake(None)  # catch up on anything committed while we were not listening
                    waited = 0.0
                    while not self._stop.is_set():
                        for n in conn.notifies(timeout=1.0):
                            if valid_id(n.payload):
                                self._wake(n.payload)
                        waited += 1.0
                        if waited >= self.poll_s:  # periodic safety poll (covers a lost NOTIFY)
                            waited = 0.0
                            self._wake(None)
            except Exception as e:
                self.connected.clear()
                if self._stop.is_set():
                    return
                logger.warning("Telemetry listener disconnected (%s); retrying in %.0fs", type(e).__name__, backoff)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_S)
