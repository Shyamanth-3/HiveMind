"""
Runs API router.
"""

from typing import Sequence
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.dependencies import get_event_bus
from app.schemas import RunCreate, RunUpdate, RunResponse
from app.services import run_service
from app.events.event_bus import EventBus

router = APIRouter(prefix="/runs", tags=["Runs"])


@router.get("/", response_model=list[RunResponse])
def get_runs(
    project_id: str | None = Query(None, description="Filter by project ID"),
    db: Session = Depends(get_db),
) -> Sequence[RunResponse]:
    """List runs, optionally filtered by project_id."""
    return run_service.get_all_runs(db, project_id=project_id)


@router.post("/", response_model=RunResponse, status_code=201)
def create_run(
    run_in: RunCreate,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
) -> RunResponse:
    """Create a new run."""
    return run_service.create_run(db, run_in, event_bus)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)) -> RunResponse:
    """Get a specific run by ID."""
    return run_service.get_run(db, run_id)


@router.patch("/{run_id}", response_model=RunResponse)
def update_run(
    run_id: str, run_in: RunUpdate, db: Session = Depends(get_db)
) -> RunResponse:
    """Update a run (e.g. status, duration)."""
    return run_service.update_run(db, run_id, run_in)
