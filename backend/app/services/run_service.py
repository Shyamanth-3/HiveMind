"""
Run service.

Handles all database operations for Runs.
Business logic goes here, keeping routers clean.
"""

from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import NAMESPACE_OID, uuid5
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import Event, Run, RunRevision, Task
from app.schemas.run import RunCreate, RunUpdate
from app.events.event_bus import EventBus
from app.events.schemas import KafkaEvent
from app.events.event_types import EventTypes


class EventBusUnavailable(Exception):
    """The run.created event could not be published; the run was recorded as failed (never left 'running')."""

    def __init__(self, run_id: str):
        super().__init__(f"event bus unavailable; run {run_id} recorded as failed")
        self.run_id = run_id


class RunStatus:
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINAL = (COMPLETED, FAILED)


def get_run(db: Session, run_id: str) -> Run:
    """Retrieve a run by ID or raise 404."""
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def get_all_runs(db: Session, project_id: str | None = None) -> Sequence[Run]:
    """Retrieve all runs, optionally filtered by project_id."""
    stmt = select(Run).order_by(Run.created_at.desc())
    if project_id:
        stmt = stmt.where(Run.project_id == project_id)
    return db.scalars(stmt).all()


def create_run(db: Session, run_in: RunCreate, event_bus: EventBus) -> Run:
    """Create a new run."""
    db_run = Run(**run_in.model_dump())
    db.add(db_run)
    db.commit()
    db.refresh(db_run)
    
    # Publish run.created event via the EventBus abstraction
    event = KafkaEvent(
        event_type=EventTypes.RUN_CREATED,
        source="run_service",
        run_id=db_run.id,
        payload={
            "project_id": db_run.project_id,
            "goal": db_run.goal,
        }
    )
    try:
        event_bus.publish(event)
    except Exception as exc:
        # No event means no pipeline will ever run: don't leave the run "running".
        db_run.status = RunStatus.FAILED
        db.commit()
        raise EventBusUnavailable(db_run.id) from exc

    return db_run


def update_run(db: Session, run_id: str, run_in: RunUpdate) -> Run:
    """Update a run partially."""
    db_run = get_run(db, run_id)
    
    update_data = run_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_run, field, value)
        
    db.commit()
    db.refresh(db_run)
    return db_run


def finish_run(db: Session, run_id: str, status: str) -> None:
    """Set a terminal status and duration (caller commits)."""
    run = db.get(Run, run_id)
    if run is None or run.status in RunStatus.TERMINAL:
        return
    run.status = status
    run.duration_ms = int((datetime.now(timezone.utc) - run.created_at).total_seconds() * 1000)
    if status == RunStatus.FAILED:  # a revision still in flight is history now, not "pending"
        db.execute(update(RunRevision).where(
            RunRevision.run_id == run_id, RunRevision.status.in_(("requested", "revised"))
        ).values(status="failed", completed_at=datetime.now(timezone.utc)))


def add_tasks_from_graph(db: Session, run_id: str, task_graph: dict, revision_number: int = 0) -> None:
    """Stage Task rows from a Builder TaskGraph payload (caller commits). Ids are deterministic per revision."""
    prefix = f"{run_id}:" if revision_number == 0 else f"{run_id}:r{revision_number}:"  # r0 keeps the Phase 1 ids
    ids = {n["id"]: str(uuid5(NAMESPACE_OID, f"{prefix}task-{n['id']}")) for n in task_graph["tasks"]}
    for n in task_graph["tasks"]:
        db.add(Task(
            id=ids[n["id"]],
            run_id=run_id,
            type="build",
            revision_number=revision_number,
            assigned_agent=n["assigned_agent"],
            title=n["title"][:255],
            description=n["description"],
            details={k: n.get(k) for k in (
                "priority", "estimated_complexity", "required_files", "acceptance_criteria")},
            depends_on=[ids[d] for d in n["dependencies"] if d in ids],
        ))


# ── Guardian revision history ───────────────────────────────────────────


def current_revision(db: Session, run_id: str) -> int:
    """Highest revision requested so far (0 = only the original Builder output exists)."""
    return db.scalar(select(func.max(RunRevision.revision_number)).where(RunRevision.run_id == run_id)) or 0


def get_revisions(db: Session, run_id: str) -> Sequence[RunRevision]:
    return db.scalars(
        select(RunRevision).where(RunRevision.run_id == run_id).order_by(RunRevision.revision_number)
    ).all()


def add_revision(db: Session, request) -> None:
    """Stage a revision row (idempotent: same deterministic id => no-op). `request` is a RevisionRequest."""
    db.execute(
        pg_insert(RunRevision).values(
            id=request.revision_id, run_id=request.run_id, revision_number=request.revision_number,
            source_review_event_id=request.source_review_event_id, reason=request.reason,
            feedback=request.feedback, requested_changes=request.requested_changes, status="requested",
            created_at=datetime.now(timezone.utc),
        ).on_conflict_do_nothing(index_elements=["id"])
    )


def set_revision_status(db: Session, run_id: str, revision_number: int, status: str, **fields) -> None:
    """Update one revision row (caller commits). No-op for revision 0 (it has no row)."""
    if revision_number < 1:
        return
    if status in ("approved", "needs_revision", "rejected", "failed"):
        fields.setdefault("completed_at", datetime.now(timezone.utc))
    db.execute(update(RunRevision).where(
        RunRevision.run_id == run_id, RunRevision.revision_number == revision_number
    ).values(status=status, **fields))


def find_stale_runs(db: Session, older_than: timedelta) -> list[dict]:
    """
    Runs still 'running' whose last activity (latest event, else creation) is older than `older_than`.

    READ-ONLY on purpose. Long LLM runs, Kafka backlogs and provider rate limits legitimately take a while, so
    nothing here fails a run automatically: it reports, an operator decides.
    """
    last_event = (
        select(func.max(Event.created_at)).where(Event.run_id == Run.id).correlate(Run).scalar_subquery()
    )
    activity = func.coalesce(last_event, Run.created_at)
    cutoff = datetime.now(timezone.utc) - older_than
    rows = db.execute(
        select(Run.id, Run.goal, Run.created_at, activity.label("last_activity"))
        .where(Run.status == RunStatus.RUNNING, activity < cutoff)
        .order_by(activity)
    ).all()
    now = datetime.now(timezone.utc)
    return [
        {"run_id": r.id, "goal": r.goal[:120], "created_at": r.created_at, "last_activity": r.last_activity,
         "idle_minutes": round((now - r.last_activity).total_seconds() / 60, 1)}
        for r in rows
    ]
