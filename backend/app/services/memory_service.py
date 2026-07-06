"""
Memory Chunk service.

Handles all database operations for MemoryChunks.
"""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MemoryChunk
from app.schemas.memory_chunk import MemoryChunkCreate


def get_chunks_by_project(db: Session, project_id: str) -> Sequence[MemoryChunk]:
    """Retrieve all memory chunks for a specific project."""
    stmt = select(MemoryChunk).where(MemoryChunk.project_id == project_id).order_by(MemoryChunk.created_at.desc())
    return db.scalars(stmt).all()


def get_all_chunks(db: Session) -> Sequence[MemoryChunk]:
    """Retrieve all memory chunks in the system."""
    stmt = select(MemoryChunk).order_by(MemoryChunk.created_at.desc())
    return db.scalars(stmt).all()


def create_chunk(db: Session, chunk_in: MemoryChunkCreate) -> MemoryChunk:
    """Create a new memory chunk."""
    db_chunk = MemoryChunk(**chunk_in.model_dump())
    db.add(db_chunk)
    db.commit()
    db.refresh(db_chunk)
    return db_chunk
