"""
Event ORM model.

Why this model exists:
An Event is an audit log entry from the Redis pub/sub event stream.
While the live event stream comes from Redis, we persist all events
to PostgreSQL for observability, debugging, and rendering the timeline.

Maps to frontend type:
Event { id, run_id, event_type, agent, payload, cost_usd, latency_ms, created_at }
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Event(Base):
    """An audit log of a system event (e.g., task_completed, plan_ready)."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: f"evt_{uuid.uuid4().hex[:12]}",  # Format mimicking mock data
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runs.id"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="e.g. run_created, plan_ready, task_completed",
    )
    agent: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Backend role key, e.g., ceo_agent (null for system events)",
    )
    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Event-specific data",
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ───────────────────────────────────────────────────
    run = relationship("Run", back_populates="events")
