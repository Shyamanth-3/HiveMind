"""
Memory API router (memory chunks). Scoped to the caller's projects; creation is rate limited and size bounded.
"""

from typing import Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.ownership import owned_project, owned_project_ids
from app.core.pagination import Page, page_params
from app.core.rate_limit import enforce
from app.db.database import get_db
from app.models import MemoryChunk, User
from app.schemas import MemoryChunkCreate, MemoryChunkResponse
from app.services import memory_service

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("/", response_model=list[MemoryChunkResponse])
def get_memory_chunks(
    project_id: str | None = Query(None, max_length=36, description="Filter by project ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: Page = Depends(page_params),
) -> Sequence[MemoryChunk]:
    stmt = select(MemoryChunk).order_by(MemoryChunk.created_at.desc())
    if project_id:
        owned_project(db, user, project_id)
        stmt = stmt.where(MemoryChunk.project_id == project_id)
    else:
        stmt = stmt.where(MemoryChunk.project_id.in_(owned_project_ids(user)))
    return db.scalars(stmt.limit(page.limit).offset(page.offset)).all()


@router.post("/", response_model=MemoryChunkResponse, status_code=201)
def create_memory_chunk(chunk_in: MemoryChunkCreate, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)) -> MemoryChunk:
    owned_project(db, user, chunk_in.project_id)
    enforce("memory", user.id, settings.RATE_LIMIT_MEMORY_PER_MIN, 60)
    return memory_service.create_chunk(db, chunk_in)
