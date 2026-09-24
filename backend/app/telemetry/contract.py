"""
WebSocket telemetry contract  (endpoint: ws://<host>/ws/runs/{run_id}[?last_event_id=<event_id>])

Rule: Kafka + PostgreSQL are the source of truth; the WebSocket is observational. Everything sent here is
derived from durable rows, and the browser can always recover from REST (`/api/v1/workflow/{id}/status`).

Server -> client messages (JSON text frames, always an object with a `type`):

  workflow.snapshot   first message on every connection.
      { type, mode: "full" | "resume", run_id, state, events: [workflow.event…], last_event_id }
      mode=full   -> `events` is the whole history (a fresh page / refresh / unknown last_event_id).
      mode=resume -> `events` holds only events AFTER the client's `last_event_id` (missed-event recovery).

  workflow.event      one persisted workflow event (sent only after its DB transaction committed).
      { type, event_id, event_type, run_id, timestamp, source, revision_number, payload }
      `event_id` is the dedup key: clients must apply each event_id at most once.
      `payload` is a compact, safe summary, never the raw Kafka payload, prompts or model output.

  workflow.state      authoritative state after a batch of events (same definition as the REST status).
      { type, run_id, state }
      state = { run_id, status, is_completed, current_stage, revision{count,max,current,status},
                agents{queen|architect|scout|builder|guardian: {status, revision, verdict?, error_type?}},
                failure: {…safe…} | null, last_event_id }

  heartbeat           every HEARTBEAT_S seconds: { type, ts }  (clients treat prolonged silence as a dead link)
  pong                reply to a client `{"type": "ping"}`.

Client -> server: only `{"type": "ping"}` is understood; everything else is ignored.

Close codes: 1008 origin not allowed (handshake rejected), 4400 malformed run id,
             4404 run does not exist, 1013 slow consumer (bounded queue overflowed, reconnect to recover).

Authentication/authorization is NOT implemented yet. `app.api.ws.authorize` is the single integration point.
"""

import re
from datetime import datetime
from typing import Any

from app.memory.security import find_secret

HEARTBEAT_S = 20.0
QUEUE_MAX = 100           # per-client outgoing queue (backpressure bound)
SEND_TIMEOUT_S = 5.0      # a socket that cannot accept a frame this long is dropped
SNAPSHOT_MAX_EVENTS = 500
NOTIFY_CHANNEL = "hivemind_events"   # PostgreSQL LISTEN/NOTIFY channel; payload = run_id

_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
# Provider account/request identifiers that appear in upstream API error messages (e.g. Groq "organization `org_...`")
_PROVIDER_IDS = re.compile(r"\b(org|req|key|proj|user)_[A-Za-z0-9]{8,}\b")


def valid_id(value: str | None) -> bool:
    """Run/event ids are short [A-Za-z0-9_-] strings. Anything else never reaches the database."""
    return bool(value) and _ID.match(value) is not None


def _text(value: Any, limit: int = 300) -> str:
    """Single-line, truncated, secret-scrubbed text for the browser."""
    s = " ".join(str(value or "").split())
    s = _PROVIDER_IDS.sub(lambda m: f"{m.group(1)}_…", s)
    if find_secret(s):
        return "[redacted]"
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _n(value: Any) -> int:
    return len(value) if isinstance(value, (list, tuple)) else 0


def revision_number_of(payload: dict) -> int | None:
    n = payload.get("revision_number")
    return n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None


def safe_failure(payload: dict | None) -> dict | None:
    """User-facing view of a run.failed payload: no stack traces, no raw feedback lists, secrets scrubbed."""
    if not payload:
        return None
    return {
        "failed_stage": _text(payload.get("failed_stage"), 40),
        "error_type": _text(payload.get("error_type"), 60),
        "message": _text(payload.get("message"), 240),
        "verdict": payload.get("verdict"),
        "revision_count": payload.get("revision_count"),
        "max_revisions": payload.get("max_revisions"),
    }


def summarize_payload(event_type: str, payload: dict) -> dict:
    """Compact summary of an event payload that is safe to send to a browser."""
    p = payload or {}
    if event_type == "run.created":
        return {"goal": _text(p.get("goal"), 200)}
    if event_type == "strategy.created":
        s = p.get("strategy") or {}
        return {"summary": _text(s.get("summary")), "phases": _n(s.get("phases"))}
    if event_type == "architecture.created":
        a = p.get("architecture_plan") or {}
        return {"summary": _text(a.get("summary")), "components": _n(a.get("components")),
                "milestones": _n(a.get("milestones"))}
    if event_type == "research.completed":
        r = p.get("research_report") or {}
        return {"summary": _text(r.get("summary")), "findings": _n(r.get("findings"))}
    if event_type == "tasks.generated":
        g = p.get("task_graph") or {}
        return {"summary": _text(g.get("summary")), "task_count": _n(g.get("tasks")),
                "revision_number": revision_number_of(p) or 0}
    if event_type == "review.completed":
        v = p.get("validation_report") or {}
        return {"verdict": v.get("overall_verdict"), "summary": _text(v.get("summary")),
                "revision_number": revision_number_of(p) or 0, "recommendations": _n(v.get("recommendations"))}
    if event_type == "revision.requested":
        r = p.get("revision") or {}
        return {"revision_number": r.get("revision_number"), "max_revisions": r.get("max_revisions"),
                "reason": _text(r.get("reason")),
                "feedback": [_text(f, 200) for f in (r.get("feedback") or [])[:5]],
                "requested_changes": _n(r.get("requested_changes")),
                "requested_changes_preview": [_text(c, 160) for c in (r.get("requested_changes") or [])[:3]]}
    if event_type == "run.completed":
        return {"verdict": p.get("verdict"), "revision_count": p.get("revision_count", 0),
                "summary": _text(p.get("summary"))}
    if event_type == "run.failed":
        return safe_failure(p) or {}
    return {}


def event_message(row: Any) -> dict:
    """`workflow.event` message for an `events` row."""
    created: datetime = row.created_at
    return {
        "type": "workflow.event",
        "event_id": row.id,
        "event_type": row.event_type,
        "run_id": row.run_id,
        "timestamp": created.isoformat(),
        "source": row.agent,
        "revision_number": revision_number_of(row.payload or {}),
        "payload": summarize_payload(row.event_type, row.payload or {}),
    }


def state_from_status(status: dict) -> dict:
    """The compact `state` object from the full REST status (single source: workflow_service)."""
    return {
        "run_id": status["run_id"],
        "status": status["status"],
        "is_completed": status["is_completed"],
        "current_stage": status["current_stage"],
        "revision": {
            "count": status["revision_count"], "max": status["max_revisions"],
            "current": status["current_revision"], "status": status["revision_status"],
        },
        "agents": status["agents"],
        "failure": safe_failure(status["failure"]),
        "last_event_id": status["last_event_id"],
    }
