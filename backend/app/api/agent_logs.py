"""
Agent Logs API router. Reads are scoped to the caller's runs (cost totals only cover the caller's runs);
writing logs is INTERNAL (administrators).
"""

from typing import Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.core.ownership import owned_project_ids, owned_run
from app.core.pagination import Page, page_params
from app.db.database import get_db
from app.models import AgentLog, Run, User
from app.schemas import AgentLogCreate, AgentLogResponse
from app.services import agent_log_service

router = APIRouter(prefix="/agent-logs", tags=["Agent Logs"])


@router.get("/", response_model=list[AgentLogResponse])
def get_agent_logs(
    run_id: str = Query(..., max_length=36, description="Run ID is required"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: Page = Depends(page_params),
) -> Sequence[AgentLog]:
    owned_run(db, user, run_id)
    stmt = select(AgentLog).where(AgentLog.run_id == run_id).order_by(AgentLog.created_at.asc())
    return db.scalars(stmt.limit(page.limit).offset(page.offset)).all()


@router.get("/cost-summary")
def get_cost_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """
    Aggregated cost for the caller's runs only.
    Returns { "total_cost_usd": float, "by_agent": { "ceo_agent": float, ... } }
    """
    mine = AgentLog.run_id.in_(select(Run.id).where(Run.project_id.in_(owned_project_ids(user))))
    rows = db.execute(select(AgentLog.agent, func.sum(AgentLog.cost_usd)).where(mine).group_by(AgentLog.agent)).all()
    by_agent = {a: float(c or 0) for a, c in rows}
    return {"total_cost_usd": sum(by_agent.values()), "by_agent": by_agent}


@router.post("/", response_model=AgentLogResponse, status_code=201)
def create_agent_log(log_in: AgentLogCreate, db: Session = Depends(get_db),
                     _admin: User = Depends(require_admin)) -> AgentLog:
    """INTERNAL (administrators only)."""
    return agent_log_service.create_log(db, log_in)
