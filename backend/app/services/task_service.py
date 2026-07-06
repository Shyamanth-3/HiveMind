"""
Task service.

Handles all database operations for Tasks.
Business logic goes here, keeping routers clean.
"""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import Task
from app.schemas.task import TaskCreate, TaskUpdate


def get_task(db: Session, task_id: str) -> Task:
    """Retrieve a task by ID or raise 404."""
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def get_tasks_by_run(db: Session, run_id: str) -> Sequence[Task]:
    """Retrieve all tasks for a specific run."""
    stmt = select(Task).where(Task.run_id == run_id).order_by(Task.created_at.asc())
    return db.scalars(stmt).all()

def get_all_tasks(db: Session) -> Sequence[Task]:
    """Retrieve all tasks system-wide."""
    stmt = select(Task).order_by(Task.created_at.asc())
    return db.scalars(stmt).all()


def create_task(db: Session, task_in: TaskCreate) -> Task:
    """Create a new task."""
    db_task = Task(**task_in.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def update_task(db: Session, task_id: str, task_in: TaskUpdate) -> Task:
    """Update a task partially."""
    db_task = get_task(db, task_id)
    
    update_data = task_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_task, field, value)
        
    db.commit()
    db.refresh(db_task)
    return db_task
