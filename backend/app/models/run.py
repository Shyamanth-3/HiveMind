"""
Run ORM model.

Why this model exists:
A Run represents a single execution of the goal-to-deliverable workflow.
When a user submits a goal like "Build a bakery website", a Run is created.
The Queen generates a plan, the Architect creates tasks, and the Run tracks
the overall status through completion.

Maps to frontend type:
Run { id, project_id, goal, plan_text, status, success_criteria, created_at, duration_ms }
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Run(Base):
    """A single execution of a user goal — contains tasks, events, and logs."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id"),
        nullable=False,
    )
    goal: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    plan_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="running",
    )
    success_criteria: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ───────────────────────────────────────────────────
    project = relationship("Project", back_populates="runs")
    tasks = relationship("Task", back_populates="run", lazy="selectin")
    events = relationship("Event", back_populates="run", lazy="selectin")
    agent_logs = relationship("AgentLog", back_populates="run", lazy="selectin")