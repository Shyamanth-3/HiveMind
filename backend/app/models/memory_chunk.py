"""
MemoryChunk ORM model.

Why this model exists:
A MemoryChunk represents a piece of knowledge stored in the system.
While this project focuses on PostgreSQL right now, eventually this
model will use pgvector to store actual embeddings for RAG capabilities.

Maps to frontend type:
MemoryChunk { id, project_id, content, embedding_dimensions, source, created_at, similarity_score }
Note: similarity_score is a computed property during retrieval, not stored.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class MemoryChunk(Base):
    """A piece of RAG knowledge stored for the organization."""

    __tablename__ = "memory_chunks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: f"mem_{uuid.uuid4().hex[:12]}",
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1536,  # Default for OpenAI ada-002 / text-embedding-3
    )
    source: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="e.g. web_search:bakery_website_best_practices",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Note: No embedding column yet. We will add pgvector in a future phase.

    # ── Relationships ───────────────────────────────────────────────────
    project = relationship("Project", back_populates="memory_chunks")
