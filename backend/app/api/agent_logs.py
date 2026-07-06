"""
Agent Logs API router.
"""

from typing import Sequence
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas import AgentLogCreate, AgentLogResponse
from app.services import agent_log_service

router = APIRouter(prefix="/agent-logs", tags=["Agent Logs"])


@router.get("/", response_model=list[AgentLogResponse])
def get_agent_logs(
    run_id: str = Query(..., description="Run ID is required"),
    db: Session = Depends(get_db),
) -> Sequence[AgentLogResponse]:
    """List all agent logs for a specific run."""
    return agent_log_service.get_logs_by_run(db, run_id)


@router.get("/cost-summary")
def get_cost_summary(db: Session = Depends(get_db)) -> dict:
    """
    Get aggregated cost data for the dashboard.
    Returns { "total_cost_usd": float, "by_agent": { "ceo_agent": float, ... } }
    """
    return {
        "total_cost_usd": agent_log_service.get_total_cost(db),
        "by_agent": agent_log_service.get_cost_by_agent(db),
    }


@router.post("/", response_model=AgentLogResponse, status_code=201)
def create_agent_log(
    log_in: AgentLogCreate, db: Session = Depends(get_db)
) -> AgentLogResponse:
    """Create a new agent log record."""
    return agent_log_service.create_log(db, log_in)
