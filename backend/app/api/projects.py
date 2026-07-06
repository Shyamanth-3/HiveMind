"""
Projects API router.
"""

from typing import Sequence
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("/", response_model=list[ProjectResponse])
def get_projects(db: Session = Depends(get_db)) -> Sequence[ProjectResponse]:
    """List all projects."""
    return project_service.get_all_projects(db)


@router.post("/", response_model=ProjectResponse, status_code=201)
def create_project(
    project_in: ProjectCreate, db: Session = Depends(get_db)
) -> ProjectResponse:
    """Create a new project."""
    return project_service.create_project(db, project_in)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectResponse:
    """Get a specific project by ID."""
    return project_service.get_project(db, project_id)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str, project_in: ProjectUpdate, db: Session = Depends(get_db)
) -> ProjectResponse:
    """Update a project."""
    return project_service.update_project(db, project_id, project_in)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a project."""
    project_service.delete_project(db, project_id)
