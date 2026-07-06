"""
Memory API router.
"""

from typing import Sequence
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas import MemoryChunkCreate, MemoryChunkResponse
from app.services import memory_service

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("/", response_model=list[MemoryChunkResponse])
def get_memory_chunks(
    project_id: str | None = Query(None, description="Filter by project ID"),
    db: Session = Depends(get_db),
) -> Sequence[MemoryChunkResponse]:
    """List memory chunks, optionally filtered by project_id."""
    if project_id:
        return memory_service.get_chunks_by_project(db, project_id)
    return memory_service.get_all_chunks(db)


@router.post("/", response_model=MemoryChunkResponse, status_code=201)
def create_memory_chunk(
    chunk_in: MemoryChunkCreate, db: Session = Depends(get_db)
) -> MemoryChunkResponse:
    """Create a new memory chunk."""
    return memory_service.create_chunk(db, chunk_in)
