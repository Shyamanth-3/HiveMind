"""
WebSocket telemetry endpoint:  /ws/runs/{run_id}[?last_event_id=<event_id>]

Contract and semantics: see app/telemetry/contract.py. This endpoint is purely observational: it reads
committed state and never influences the workflow.

Security (in this order, all enforced before any run data is sent):
  1. Origin allowlist (browsers do not apply CORS to WebSockets; an extra control, never the only one)
  2. authentication: the session cookie / Bearer header sent with the handshake (never a credential in the URL)
  3. ownership: the caller must own the project of `run_id`; an unowned run is indistinguishable from a missing one
"""

import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.core.auth import get_ws_user, origin_is_trusted
from app.core.config import settings
from app.core.ownership import user_owns_run
from app.db.database import SessionLocal
from app.models import User
from app.telemetry.contract import valid_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Telemetry"])


def origin_allowed(websocket: WebSocket) -> bool:
    """Browser requests must come from a configured origin (CORS_ORIGINS); non-browser clients send no Origin."""
    origin = websocket.headers.get("origin")
    return origin is None or origin_is_trusted(origin)


def _owns(user: User, run_id: str) -> bool:
    with SessionLocal() as db:
        return user_owns_run(db, user.id, run_id)


@router.websocket("/ws/runs/{run_id}")
async def run_telemetry(
    websocket: WebSocket,
    run_id: str,
    last_event_id: str | None = Query(default=None),
    user: User | None = Depends(get_ws_user),
) -> None:
    if not origin_allowed(websocket) or user is None:
        await websocket.close(code=1008)  # rejected during the handshake (HTTP 403); nothing is revealed
        return
    await websocket.accept()
    # Ids are validated before they can reach a query. Close codes are visible to browser clients only after accept().
    if not valid_id(run_id) or (last_event_id is not None and not valid_id(last_event_id)):
        await websocket.close(code=4400, reason="invalid id")
        return
    if not _owns(user, run_id):  # same answer as an unknown run
        await websocket.close(code=4404, reason="run not found")
        return

    hub = getattr(websocket.app.state, "telemetry_hub", None)
    if hub is None:
        await websocket.close(code=1011, reason="telemetry unavailable")
        return

    client = await hub.connect(websocket, run_id, last_event_id)
    if client is None:  # 4404 / 1011 already sent
        return
    try:
        while True:  # the sender/heartbeat tasks write; this loop only reads (and detects disconnects)
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "ping":
                hub.send(client, {"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:  # never leak internals to the client
        logger.exception("Telemetry socket error for run %s", run_id)
    finally:
        await hub.disconnect(client)
