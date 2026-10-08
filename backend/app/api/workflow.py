from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.core.ownership import owned_run
from app.db.database import get_db
from app.models import User
from app.services import event_service, run_service
from app.events.event_types import EventTypes
from app.core.config import settings
from datetime import timedelta

from app.services.workflow_service import build_workflow_status

router = APIRouter(prefix="/workflow", tags=["Workflow"])

@router.get("/stale")
def list_stale_runs(older_than_minutes: int = Query(default=None, ge=1, le=10_080), db: Session = Depends(get_db),
                    _admin: User = Depends(require_admin)) -> dict[str, Any]:
    """
    INTERNAL (administrators only): covers every user's runs.
    Runs still 'running' with no event for `older_than_minutes` (default STALE_RUN_MINUTES). Report only:
    HiveMind never auto-fails a long-running run; see docs/PROJECT-STATUS.md (Phase 5, stale-run policy).
    """
    minutes = older_than_minutes or settings.STALE_RUN_MINUTES
    return {"older_than_minutes": minutes, "runs": run_service.find_stale_runs(db, timedelta(minutes=minutes))}


@router.get("/{run_id}/status")
def get_workflow_status(run_id: str, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get the current progress of a workflow run (same definition the WebSocket snapshot uses)."""
    owned_run(db, user, run_id)
    return build_workflow_status(db, run_id)


@router.get("/{run_id}/outputs")
def get_workflow_outputs(run_id: str, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get the accumulated outputs from all agents in the workflow run."""
    run = owned_run(db, user, run_id)
    events = event_service.get_events_by_run(db, run_id)
    
    outputs = {}
    for event in events:
        if event.event_type == EventTypes.STRATEGY_CREATED:
            outputs["strategy"] = event.payload.get("strategy")
        elif event.event_type == EventTypes.ARCHITECTURE_CREATED:
            outputs["architecture_plan"] = event.payload.get("architecture_plan")
        elif event.event_type == EventTypes.RESEARCH_COMPLETED:
            outputs["research_report"] = event.payload.get("research_report")
        elif event.event_type == EventTypes.TASKS_GENERATED:
            outputs["task_graph"] = event.payload.get("task_graph")
        elif event.event_type == EventTypes.REVIEW_COMPLETED:
            outputs["validation_report"] = event.payload.get("validation_report")
            
    return {
        "run_id": run.id,
        "goal": run.goal,
        "current_revision": run_service.current_revision(db, run_id),
        "outputs": outputs
    }
