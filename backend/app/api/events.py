"""
Events API router.
"""

from typing import Sequence
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas import EventCreate, EventResponse
from app.services import event_service

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("/", response_model=list[EventResponse])
def get_events(
    run_id: str = Query(..., description="Run ID is required"),
    db: Session = Depends(get_db),
) -> Sequence[EventResponse]:
    """List all events for a specific run."""
    return event_service.get_events_by_run(db, run_id)


@router.get("/recent", response_model=list[EventResponse])
def get_recent_events(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Sequence[EventResponse]:
    """Get the most recent system-wide events (for dashboard feed)."""
    return event_service.get_recent_events(db, limit)


@router.post("/", response_model=EventResponse, status_code=201)
def create_event(
    event_in: EventCreate, db: Session = Depends(get_db)
) -> EventResponse:
    """Create a new event record."""
    return event_service.create_event(db, event_in)
