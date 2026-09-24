"""
RunRevision ORM model: one row per Guardian-requested revision of a run (history is never overwritten).

Revision 0 is the original Builder output and has no row; its tasks carry revision_number=0.
Row N answers: which Guardian review asked for it (source_review_event_id), what was asked
(feedback / requested_changes), which Builder output followed (tasks_event_id) and which review
judged that output (review_event_id, status).

status: requested -> revised -> approved | needs_revision | rejected   (failed if the run fails mid-way)
"""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

REVISION_STATUSES = ("requested", "revised", "approved", "needs_revision", "rejected", "failed")


class RunRevision(Base):
    __tablename__ = "run_revisions"
    __table_args__ = (
        UniqueConstraint("run_id", "revision_number", name="uq_run_revisions_run_number"),
        CheckConstraint("revision_number >= 1", name="ck_run_revisions_number"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in REVISION_STATUSES) + ")",
            name="ck_run_revisions_status",
        ),
        Index("ix_run_revisions_run_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        comment="Deterministic: uuid5(run_id : source_review_event_id : revision_number)",
    )
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_review_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[list] = mapped_column(JSON, nullable=False)
    requested_changes: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    tasks_event_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="tasks.generated event with the Builder output for this revision")
    review_event_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="review.completed event that judged this revision's output")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run = relationship("Run")
