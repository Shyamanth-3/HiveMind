"""
Tasks API router.
"""

from typing import Sequence
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas import TaskCreate, TaskUpdate, TaskResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/", response_model=list[TaskResponse])
def get_tasks(
    run_id: str | None = Query(None, description="Run ID is optional"),
    db: Session = Depends(get_db),
) -> Sequence[TaskResponse]:
    """List tasks, optionally filtered by run_id."""
    if run_id:
        return task_service.get_tasks_by_run(db, run_id)
    return task_service.get_all_tasks(db)


@router.post("/", response_model=TaskResponse, status_code=201)
def create_task(
    task_in: TaskCreate, db: Session = Depends(get_db)
) -> TaskResponse:
    """Create a new task."""
    return task_service.create_task(db, task_in)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskResponse:
    """Get a specific task by ID."""
    return task_service.get_task(db, task_id)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str, task_in: TaskUpdate, db: Session = Depends(get_db)
) -> TaskResponse:
    """Update a task status or result."""
    return task_service.update_task(db, task_id, task_in)
