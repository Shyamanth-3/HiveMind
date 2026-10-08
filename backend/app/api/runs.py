"""
Runs API router. A run belongs to the user who owns its project; everything else is 404.
"""

import logging
from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.core.config import settings
from app.core.dependencies import get_event_bus
from app.core.ownership import owned_project, owned_project_ids, owned_run
from app.core.pagination import Page, page_params
from app.core.rate_limit import enforce
from app.db.database import get_db
from app.events.event_bus import EventBus
from app.models import Run, User
from app.schemas import RunCreate, RunResponse, RunUpdate
from app.services import run_service
from app.services.run_service import EventBusUnavailable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["Runs"])


@router.get("/", response_model=list[RunResponse])
def get_runs(
    project_id: str | None = Query(None, max_length=36, description="Filter by project ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: Page = Depends(page_params),
) -> Sequence[Run]:
    """List the caller's runs, optionally for one of their projects."""
    stmt = select(Run).where(Run.project_id.in_(owned_project_ids(user))).order_by(Run.created_at.desc())
    if project_id:
        stmt = stmt.where(Run.project_id == project_id)
    return db.scalars(stmt.limit(page.limit).offset(page.offset)).all()


@router.post("/", response_model=RunResponse, status_code=201)
def create_run(
    run_in: RunCreate,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    user: User = Depends(get_current_user),
) -> Run:
    """Create a run in one of the caller's projects (every run triggers paid LLM calls: rate limited)."""
    owned_project(db, user, run_in.project_id)
    enforce("runs", user.id, settings.RATE_LIMIT_RUNS_PER_HOUR, 3600)
    try:
        run = run_service.create_run(db, run_in, event_bus)
        logger.info("Run created | run=%s user=%s project=%s", run.id, user.id, run.project_id)
        return run
    except EventBusUnavailable as e:
        raise HTTPException(status_code=503, detail={
            "message": "The event bus is unavailable; the run was recorded as failed. Retry later.",
            "run_id": e.run_id,
        })


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Run:
    return owned_run(db, user, run_id)


@router.patch("/{run_id}", response_model=RunResponse)
def update_run(run_id: str, run_in: RunUpdate, db: Session = Depends(get_db),
               _admin: User = Depends(require_admin)) -> Run:
    """INTERNAL (administrators only): the run lifecycle is driven by the Scheduler, never by end users."""
    return run_service.update_run(db, run_id, run_in)
