"""
Agent Log service.

Handles all database operations for AgentLogs, including cost aggregations.
"""

from typing import Sequence
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import AgentLog
from app.schemas.agent_log import AgentLogCreate


def get_logs_by_run(db: Session, run_id: str) -> Sequence[AgentLog]:
    """Retrieve all agent logs for a specific run."""
    stmt = select(AgentLog).where(AgentLog.run_id == run_id).order_by(AgentLog.created_at.asc())
    return db.scalars(stmt).all()


def get_total_cost(db: Session) -> float:
    """Calculate the total cost across all LLM calls in USD."""
    result = db.scalar(select(func.sum(AgentLog.cost_usd)))
    return float(result) if result else 0.0


def get_cost_by_agent(db: Session) -> dict[str, float]:
    """Calculate the total cost grouped by agent role."""
    stmt = select(AgentLog.agent, func.sum(AgentLog.cost_usd)).group_by(AgentLog.agent)
    results = db.execute(stmt).all()
    return {row[0]: float(row[1]) for row in results}


def create_log(db: Session, log_in: AgentLogCreate) -> AgentLog:
    """Create a new agent log record."""
    db_log = AgentLog(**log_in.model_dump())
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log
