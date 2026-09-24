"""
Event service.

Handles all database operations for Events.
Events are typically immutable once created.
"""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.schemas import KafkaEvent
from app.models import Event
from app.schemas.event import EventCreate


def get_events_by_run(db: Session, run_id: str) -> Sequence[Event]:
    """Retrieve all events for a specific run, ordered chronologically."""
    stmt = select(Event).where(Event.run_id == run_id).order_by(Event.created_at.asc(), Event.id.asc())
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



def event_exists(db: Session, event_id: str) -> bool:
    """True if a Kafka event with this event_id was already processed."""
    return db.get(Event, event_id) is not None


def add_kafka_event(db: Session, event: KafkaEvent) -> Event:
    """
    Stage a Kafka event in the events table (caller commits).

    The Kafka event_id is the primary key, so the table doubles as the
    processed-event ledger: inserting the same event twice violates the PK.
    """
    db_event = Event(
        id=str(event.event_id),
        run_id=event.run_id,
        event_type=getattr(event.event_type, "value", event.event_type),
        agent=event.source,
        payload=event.payload,
        created_at=event.timestamp,
    )
    db.add(db_event)
    return db_event
