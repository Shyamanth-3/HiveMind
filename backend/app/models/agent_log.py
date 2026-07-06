"""
AgentLog ORM model.

Why this model exists:
Every time an agent executes an LLM call, we record it. This is the
foundation of the system's observability, allowing us to build the
Cost Breakdown Chart and monitor latency/success rates.

Maps to frontend type:
AgentLog { run_id, task_id, agent, prompt_tokens, completion_tokens, cost_usd, latency_ms, outcome, model }
Note: Frontend mock doesn't show an ID, but DB needs a primary key.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class AgentLog(Base):
    """Detailed observability record for a single LLM API call."""

    __tablename__ = "agent_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: f"log_{uuid.uuid4().hex[:12]}",
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runs.id"),
        nullable=False,
    )
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id"),
        nullable=False,
    )
    agent: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Backend role key",
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    cost_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    outcome: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="success, retried, failed",
    )
    model: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="e.g. gemini-2.0-flash",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ───────────────────────────────────────────────────
    run = relationship("Run", back_populates="agent_logs")
    task = relationship("Task")
