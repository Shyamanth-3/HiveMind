"""
AgentMemory ORM model.

A durable, project-scoped piece of knowledge stored by an agent, with a pgvector embedding for
semantic retrieval (cosine distance, HNSW index).

Scope:      project_id (retrieval never crosses projects; there is no user identity yet)
Provenance: agent, run_id, source_event_id, created_at
Dedup:      unique (project_id, memory_type, content_hash) on normalised content
Conflicts:  no supersede logic; conflicting memories are both kept, with provenance
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.database import Base

MEMORY_TYPES = ("fact", "decision", "preference", "context", "lesson")


class AgentMemory(Base):
    """A piece of semantic memory stored by an agent."""

    __tablename__ = "agent_memories"
    __table_args__ = (
        CheckConstraint(
            "memory_type IN (" + ", ".join(f"'{t}'" for t in MEMORY_TYPES) + ")",
            name="ck_agent_memories_type",
        ),
        CheckConstraint("importance BETWEEN 1 AND 5", name="ck_agent_memories_importance"),
        Index("uq_agent_memories_scope_hash", "project_id", "memory_type", "content_hash", unique=True),
        Index(
            "ix_agent_memories_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: f"mem_{uuid.uuid4().hex[:12]}",
    )
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("runs.id"), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent: Mapped[str] = mapped_column(String(50), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, default="context")
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3, server_default="3")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.EMBEDDING_DIMENSION), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ───────────────────────────────────────────────────
    run = relationship("Run", backref="memories")
