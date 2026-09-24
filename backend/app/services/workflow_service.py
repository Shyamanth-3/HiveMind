"""
Workflow state: the single definition of "where is this run" used by BOTH the REST API
(/workflow/{id}/status) and the WebSocket telemetry (snapshot + state messages).

Everything here is derived from the durable `events` / `run_revisions` / `runs` rows. Nothing is
kept in memory, so the REST API, a WebSocket snapshot and a page refresh always agree.
"""

from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.core.config import settings
from app.events.event_types import EventTypes
from app.models import Event
from app.services import event_service, run_service
from app.services.run_service import RunStatus

# Standard progression of the pipeline
WORKFLOW_STAGES = [
    EventTypes.RUN_CREATED,
    EventTypes.STRATEGY_CREATED,
    EventTypes.ARCHITECTURE_CREATED,
    EventTypes.RESEARCH_COMPLETED,
    EventTypes.TASKS_GENERATED,
    EventTypes.REVIEW_COMPLETED,
    EventTypes.RUN_COMPLETED,
]

AGENT_ORDER = ["queen", "architect", "scout", "builder", "guardian"]


def _revision_of(payload: dict) -> int:
    n = payload.get("revision_number")
    return n if isinstance(n, int) and n >= 0 else 0


def verdict_of(event: Event) -> str | None:
    report = event.payload.get("validation_report")
    return report.get("overall_verdict") if isinstance(report, dict) else None


def compute_agent_states(events: Sequence[Event], run_status: str) -> dict[str, dict[str, Any]]:
    """
    Per-agent lifecycle from real events (never from timers):
      pending | running | completed | revision (Guardian asked for changes) | failed
    `revision` is the revision number the agent last worked on / reviewed (0 = original output).

    How to read the events: the Scheduler persists an event only AFTER the handler that CONSUMED it has finished
    (that handler produced the next event). So a persisted event means "its consumer is done, and the next agent
    is running right now":
        run.created          Queen done          -> Architect running
        strategy.created     Architect done      -> Scout running
        architecture.created Scout done          -> Builder running
        research.completed   Builder done        -> Guardian running
        tasks.generated      Guardian done       (the verdict arrives with review.completed, milliseconds later)
        review.completed     needs_revision      -> Builder running the revision (rev n+1)
        revision.requested   Builder done (rev)  -> Guardian running the re-review
    """
    st: dict[str, dict[str, Any]] = {a: {"status": "pending", "revision": 0} for a in AGENT_ORDER}

    def done(agent: str, **extra: Any) -> None:
        st[agent].update(status="completed", **extra)

    def start(agent: str, **extra: Any) -> None:
        st[agent].update(status="running", **extra)

    if not events and run_status == RunStatus.RUNNING:
        start("queen")  # the run exists and is queued/being handled by the Queen
    for e in events:
        t, n = e.event_type, _revision_of(e.payload)
        if t == EventTypes.RUN_CREATED:
            done("queen")
            start("architect")
        elif t == EventTypes.STRATEGY_CREATED:
            done("architect")
            start("scout")
        elif t == EventTypes.ARCHITECTURE_CREATED:
            done("scout")
            start("builder", revision=0)
        elif t == EventTypes.RESEARCH_COMPLETED:
            done("builder", revision=0)
            start("guardian", revision=0)
        elif t == EventTypes.TASKS_GENERATED:
            done("guardian", revision=n)
        elif t == EventTypes.REVIEW_COMPLETED:
            v = verdict_of(e)
            st["guardian"].update(status="revision" if v == "needs_revision" else "completed", revision=n, verdict=v)
            if v == "needs_revision":
                start("builder", revision=n + 1)  # the revision request is already queued for the Builder
        elif t == EventTypes.REVISION_REQUESTED:
            done("builder", revision=n)
            start("guardian", revision=n, verdict=None)
        elif t == EventTypes.RUN_FAILED:
            stage = e.payload.get("failed_stage")
            if stage in st:
                idx = AGENT_ORDER.index(stage)
            else:  # e.g. "scheduler": blame whoever was running
                idx = next((i for i, a in enumerate(AGENT_ORDER) if st[a]["status"] == "running"), None)
            if idx is not None:
                for i, a in enumerate(AGENT_ORDER):
                    if i == idx:
                        st[a].update(status="failed", error_type=e.payload.get("error_type"))
                    elif st[a]["status"] == "running":
                        # a later agent was only speculatively "next"; an earlier one had in fact finished
                        st[a]["status"] = "pending" if i > idx else "completed"
    if run_status == RunStatus.COMPLETED:  # nothing may still look "running" once the run is done
        for a in AGENT_ORDER:
            if st[a]["status"] == "running":
                st[a]["status"] = "completed"
    return st


def current_stage_of(events: Sequence[Event], run_status: str) -> str | None:
    """Next expected event, from the LAST event (stages repeat during revisions)."""
    if run_status != RunStatus.RUNNING:
        return None
    if not events:
        return WORKFLOW_STAGES[0]
    last = events[-1]
    if last.event_type == EventTypes.REVIEW_COMPLETED:
        v = verdict_of(last)
        return (EventTypes.RUN_COMPLETED if v == "approved"
                else EventTypes.REVISION_REQUESTED if v == "needs_revision" else EventTypes.RUN_FAILED)
    if last.event_type == EventTypes.REVISION_REQUESTED:
        return EventTypes.TASKS_GENERATED
    if last.event_type in WORKFLOW_STAGES:
        nxt = WORKFLOW_STAGES.index(last.event_type) + 1
        return WORKFLOW_STAGES[nxt] if nxt < len(WORKFLOW_STAGES) else None
    return None


def build_workflow_status(db: Session, run_id: str) -> dict[str, Any]:
    """The authoritative workflow state for a run (raises 404 via get_run if it does not exist)."""
    run = run_service.get_run(db, run_id)
    events = event_service.get_events_by_run(db, run_id)
    revisions = run_service.get_revisions(db, run_id)
    latest = events[-1] if events else None
    failure = next((e.payload for e in reversed(events) if e.event_type == EventTypes.RUN_FAILED), None)

    last_activity = latest.created_at if latest else run.created_at
    idle_s = max(0.0, (datetime.now(timezone.utc) - last_activity).total_seconds())
    return {
        "run_id": run.id,
        "goal": run.goal,
        "status": run.status,
        "idle_seconds": round(idle_s),
        "stale": run.status == RunStatus.RUNNING and idle_s > settings.STALE_RUN_MINUTES * 60,
        "is_completed": run.status == RunStatus.COMPLETED,
        "revision_count": len(revisions),
        "max_revisions": settings.MAX_REVISIONS,
        "current_revision": revisions[-1].revision_number if revisions else 0,
        "revision_status": revisions[-1].status if revisions else "none",
        "revisions": [
            {"revision_number": r.revision_number, "revision_id": r.id, "status": r.status,
             "source_review_event_id": r.source_review_event_id, "review_event_id": r.review_event_id,
             "tasks_event_id": r.tasks_event_id, "reason": r.reason, "feedback": r.feedback,
             "requested_changes": r.requested_changes, "created_at": r.created_at,
             "completed_at": r.completed_at}
            for r in revisions
        ],
        "failure": failure,
        "current_stage": current_stage_of(events, run.status),
        "agents": compute_agent_states(events, run.status),
        "completed_stages": [e.event_type for e in events],
        "latest_event_type": latest.event_type if latest else None,
        "last_event_id": latest.id if latest else None,
        "updated_at": latest.created_at if latest else run.created_at,
    }
