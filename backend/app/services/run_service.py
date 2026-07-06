"""
Run service.

Handles all database operations for Runs.
Business logic goes here, keeping routers clean.
"""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import Run
from app.schemas.run import RunCreate, RunUpdate


def get_run(db: Session, run_id: str) -> Run:
    """Retrieve a run by ID or raise 404."""
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def get_all_runs(db: Session, project_id: str | None = None) -> Sequence[Run]:
    """Retrieve all runs, optionally filtered by project_id."""
    stmt = select(Run).order_by(Run.created_at.desc())
    if project_id:
        stmt = stmt.where(Run.project_id == project_id)
    return db.scalars(stmt).all()


def create_run(db: Session, run_in: RunCreate) -> Run:
    """Create a new run."""
    db_run = Run(**run_in.model_dump())
    db.add(db_run)
    db.commit()
    db.refresh(db_run)
    return db_run


def update_run(db: Session, run_id: str, run_in: RunUpdate) -> Run:
    """Update a run partially."""
    db_run = get_run(db, run_id)
    
    update_data = run_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_run, field, value)
        
    db.commit()
    db.refresh(db_run)
    return db_run
