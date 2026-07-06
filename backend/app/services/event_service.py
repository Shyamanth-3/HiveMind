"""
Event service.

Handles all database operations for Events.
Events are typically immutable once created.
"""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event
from app.schemas.event import EventCreate


def get_events_by_run(db: Session, run_id: str) -> Sequence[Event]:
    """Retrieve all events for a specific run, ordered chronologically."""
    stmt = select(Event).where(Event.run_id == run_id).order_by(Event.created_at.asc())
    return db.scalars(stmt).all()


def get_recent_events(db: Session, limit: int = 20) -> Sequence[Event]:
    """Retrieve the most recent system-wide events for the dashboard feed."""
    stmt = select(Event).order_by(Event.created_at.desc()).limit(limit)
    return db.scalars(stmt).all()


def create_event(db: Session, event_in: EventCreate) -> Event:
    """Create a new event record."""
    db_event = Event(**event_in.model_dump())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event
