"""
Project service.

Handles all database operations for Projects.
Business logic goes here, keeping routers clean.
"""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


def get_project(db: Session, project_id: str) -> Project:
    """Retrieve a project by ID or raise 404."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def get_all_projects(db: Session) -> Sequence[Project]:
    """Retrieve all projects, ordered by creation date descending."""
    stmt = select(Project).order_by(Project.created_at.desc())
    return db.scalars(stmt).all()


def create_project(db: Session, project_in: ProjectCreate) -> Project:
    """Create a new project."""
    db_project = Project(**project_in.model_dump())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


def update_project(db: Session, project_id: str, project_in: ProjectUpdate) -> Project:
    """Update a project partially."""
    db_project = get_project(db, project_id)
    
    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_project, field, value)
        
    db.commit()
    db.refresh(db_project)
    return db_project


def delete_project(db: Session, project_id: str) -> None:
    """Delete a project by ID."""
    db_project = get_project(db, project_id)
    db.delete(db_project)
    db.commit()
