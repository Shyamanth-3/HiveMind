"""
Task ORM model.

Why this model exists:
A Task is a single unit of work assigned to an agent within a Run.
Tasks form a DAG (Directed Acyclic Graph) — each task may depend on
other tasks completing before it can execute. The Scheduler evaluates
these dependencies to determine task readiness.

Maps to frontend type:
Task { id, run_id, type, assigned_agent, depends_on, status, result, retry_count }
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Task(Base):
    """A single unit of work in the task DAG, assigned to one agent."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runs.id"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Task type: plan, breakdown, research, build, review",
    )
    assigned_agent: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Backend role key: ceo_agent, pm_agent, etc.",
    )
    depends_on: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="List of task IDs this task depends on",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )
    result: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ───────────────────────────────────────────────────
    run = relationship("Run", back_populates="tasks")
