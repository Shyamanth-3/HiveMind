"""
Events API router. Reads are scoped to the caller's runs. Writing events is INTERNAL (administrators): the events
table is the Scheduler's processed-event ledger and the source of WebSocket telemetry, so users must not forge rows.
"""

from typing import Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.core.ownership import owned_project_ids, owned_run
from app.core.pagination import Page, page_params
from app.db.database import get_db
from app.models import Event, Run, User
from app.schemas import EventCreate, EventResponse
from app.services import event_service

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("/", response_model=list[EventResponse])
def get_events(
    run_id: str = Query(..., max_length=36, description="Run ID is required"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: Page = Depends(page_params),
) -> Sequence[Event]:
    owned_run(db, user, run_id)
    stmt = select(Event).where(Event.run_id == run_id).order_by(Event.created_at.asc(), Event.id.asc())
    return db.scalars(stmt.limit(page.limit).offset(page.offset)).all()


@router.get("/recent", response_model=list[EventResponse])
def get_recent_events(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Sequence[Event]:
    """The caller's most recent events (dashboard feed)."""
    mine = select(Run.id).where(Run.project_id.in_(owned_project_ids(user)))
    return db.scalars(select(Event).where(Event.run_id.in_(mine)).order_by(Event.created_at.desc()).limit(limit)).all()


@router.post("/", response_model=EventResponse, status_code=201)
def create_event(event_in: EventCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> Event:
    """INTERNAL (administrators only)."""
    return event_service.create_event(db, event_in)
