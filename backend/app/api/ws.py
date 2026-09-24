"""
WebSocket telemetry endpoint:  /ws/runs/{run_id}[?last_event_id=<event_id>]

Contract and semantics: see app/telemetry/contract.py. This endpoint is purely observational: it reads
committed state and never influences the workflow.
"""

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.telemetry.contract import valid_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Telemetry"])


def origin_allowed(websocket: WebSocket) -> bool:
    """
    Browsers do not apply CORS to WebSockets, so any web page could otherwise open this socket. Browser
    requests must come from a configured origin (CORS_ORIGINS); non-browser clients send no Origin header.
    """
    origin = websocket.headers.get("origin")
    return origin is None or origin.rstrip("/") in settings.cors_origin_list


def authorize(websocket: WebSocket, run_id: str) -> bool:
    """
    THE authentication/authorization integration point (not implemented yet: HiveMind has no user identity).
    A future phase checks the caller's credentials and their access to `run_id` here.
    """
    return origin_allowed(websocket)


@router.websocket("/ws/runs/{run_id}")
async def run_telemetry(websocket: WebSocket, run_id: str, last_event_id: str | None = Query(default=None)) -> None:
    if not authorize(websocket, run_id):
        await websocket.close(code=1008)  # rejected during the handshake
        return
    await websocket.accept()
    # Ids are validated before they can reach a query. Close codes are visible to browser clients only after accept().
    if not valid_id(run_id) or (last_event_id is not None and not valid_id(last_event_id)):
        await websocket.close(code=4400, reason="invalid id")
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
