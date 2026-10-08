"""
Resource ownership. A project belongs to one user; runs, tasks, events, revisions and memories belong to the user of
their project. Lookups by id NEVER bypass this: a resource the caller does not own is reported as 404 (not 403), so
UUID guessing cannot even confirm that something exists. Enforced here, in the backend, never by the frontend.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project, Run, Task, User

NOT_FOUND = HTTPException(status_code=404, detail="Not found")


def owned_project(db: Session, user: User, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise NOT_FOUND
    return project


def owned_run(db: Session, user: User, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise NOT_FOUND
    owned_project(db, user, run.project_id)
    return run


def owned_task(db: Session, user: User, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NOT_FOUND
    owned_run(db, user, task.run_id)
    return task


def user_owns_run(db: Session, user_id: str, run_id: str) -> bool:
    """Non-raising variant for the WebSocket endpoint."""
    return db.scalar(
        select(Project.id).join(Run, Run.project_id == Project.id).where(Run.id == run_id, Project.owner_id == user_id)
    ) is not None


def owned_project_ids(user: User):
    """Sub-select of the caller's project ids, for filtering list queries."""
    return select(Project.id).where(Project.owner_id == user.id)
