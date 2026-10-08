"""
Projects API router. Every project belongs to the authenticated user; other users' projects are invisible (404).
"""

from typing import Sequence

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.ownership import owned_project
from app.core.pagination import Page, page_params
from app.db.database import get_db
from app.models import Project, User
from app.schemas import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("/", response_model=list[ProjectResponse])
def get_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                 page: Page = Depends(page_params)) -> Sequence[Project]:
    """List the caller's projects."""
    stmt = (select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc())
            .limit(page.limit).offset(page.offset))
    return db.scalars(stmt).all()


@router.post("/", response_model=ProjectResponse, status_code=201)
def create_project(project_in: ProjectCreate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> Project:
    """Create a project owned by the caller."""
    project = Project(**project_in.model_dump(), owner_id=user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Project:
    return owned_project(db, user, project_id)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, project_in: ProjectUpdate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> Project:
    project = owned_project(db, user, project_id)
    for field, value in project_in.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    db.delete(owned_project(db, user, project_id))
    db.commit()
