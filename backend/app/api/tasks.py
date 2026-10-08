"""
Tasks API router. Reads are scoped to the caller's runs; task creation/updates are INTERNAL (administrators).
"""

from typing import Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.core.ownership import owned_project_ids, owned_run, owned_task
from app.core.pagination import Page, page_params
from app.db.database import get_db
from app.models import Run, Task, User
from app.schemas import TaskCreate, TaskResponse, TaskUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/", response_model=list[TaskResponse])
def get_tasks(
    run_id: str | None = Query(None, max_length=36, description="Run ID is optional"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: Page = Depends(page_params),
) -> Sequence[Task]:
    stmt = select(Task).order_by(Task.revision_number, Task.id)
    if run_id:
        owned_run(db, user, run_id)
        stmt = stmt.where(Task.run_id == run_id)
    else:
        stmt = stmt.where(Task.run_id.in_(select(Run.id).where(Run.project_id.in_(owned_project_ids(user)))))
    return db.scalars(stmt.limit(page.limit).offset(page.offset)).all()


@router.post("/", response_model=TaskResponse, status_code=201)
def create_task(task_in: TaskCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> Task:
    """INTERNAL (administrators only)."""
    return task_service.create_task(db, task_in)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Task:
    return owned_task(db, user, task_id)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, task_in: TaskUpdate, db: Session = Depends(get_db),
                _admin: User = Depends(require_admin)) -> Task:
    """INTERNAL (administrators only)."""
    return task_service.update_task(db, task_id, task_in)
