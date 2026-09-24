"""
Database side of the telemetry: read-only queries over the durable `events` history.

A client's position is a cursor = the (created_at, id) of the last event it has received, the same
ordering `event_service.get_events_by_run` uses. Snapshot, missed-event recovery and live delivery are
all "give me this run's events after cursor X", so they can never disagree.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.models import Event, Run
from app.services.workflow_service import build_workflow_status
from app.telemetry.contract import SNAPSHOT_MAX_EVENTS, event_message, state_from_status

Cursor = tuple[datetime, str]


class RunNotFound(Exception):
    pass


def cursor_of(event: Event) -> Cursor:
    return (event.created_at, event.id)


def resolve_cursor(db: Session, run_id: str, event_id: str | None) -> Cursor | None:
    """Cursor for a client-supplied last_event_id; None if unknown or not an event of THIS run."""
    if not event_id:
        return None
    ev = db.get(Event, event_id)
    return cursor_of(ev) if ev is not None and ev.run_id == run_id else None


def events_after(db: Session, run_id: str, cursor: Cursor | None, limit: int = SNAPSHOT_MAX_EVENTS) -> list[Event]:
    stmt = select(Event).where(Event.run_id == run_id)
    if cursor is not None:
        stmt = stmt.where(tuple_(Event.created_at, Event.id) > tuple_(cursor[0], cursor[1]))
    return list(db.scalars(stmt.order_by(Event.created_at.asc(), Event.id.asc()).limit(limit)))


def build_snapshot(db: Session, run_id: str, last_event_id: str | None) -> tuple[dict, Cursor | None]:
    """
    (`workflow.snapshot` message, delivery cursor). Raises RunNotFound.
    With a valid last_event_id: only the events after it (mode=resume), else the full history (mode=full).
    """
    if db.get(Run, run_id) is None:
        raise RunNotFound(run_id)
    since = resolve_cursor(db, run_id, last_event_id)
    events = events_after(db, run_id, since)
    status = build_workflow_status(db, run_id)
    snapshot = {
        "type": "workflow.snapshot",
        "mode": "resume" if since is not None else "full",
        "run_id": run_id,
        "state": state_from_status(status),
        "events": [event_message(e) for e in events],
        "last_event_id": events[-1].id if events else (last_event_id if since is not None else None),
    }
    return snapshot, (cursor_of(events[-1]) if events else since)


def fetch_updates(db: Session, run_id: str, cursor: Cursor | None) -> tuple[list[dict], dict | None, Cursor | None]:
    """New event messages after `cursor` + the fresh state (None when nothing new) + the advanced cursor."""
    events = events_after(db, run_id, cursor)
    if not events:
        return [], None, cursor
    state = state_from_status(build_workflow_status(db, run_id))
    return [event_message(e) for e in events], state, cursor_of(events[-1])
