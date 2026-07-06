"""
Project ORM model.

Why this model exists:
A Project is the top-level container in HiveMind. Every Run belongs to
a Project. The frontend uses Project to group runs and display them on
the dashboard and runs page.

Maps to frontend type: Project { id, name, owner, created_at, goal_summary }
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Project(Base):
    """A top-level container for runs — e.g. 'Bakery Marketing Site'."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    owner: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    goal_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ───────────────────────────────────────────────────
    runs = relationship("Run", back_populates="project", lazy="selectin")
    memory_chunks = relationship(
        "MemoryChunk", back_populates="project", lazy="selectin"
    )
