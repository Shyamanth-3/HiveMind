"""
System API router.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.models import User
from app.schemas import AgentStatusResponse, SystemServiceResponse
from app.services import system_service

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/agents", response_model=list[AgentStatusResponse])
def get_agents_status(_user: User = Depends(get_current_user)) -> list[AgentStatusResponse]:
    """Get the current operational status of all agents."""
    return system_service.get_agent_statuses()


@router.get("/services", response_model=list[SystemServiceResponse])
def get_services_status(db: Session = Depends(get_db),
                        _user: User = Depends(get_current_user)) -> list[SystemServiceResponse]:
    """Check infrastructure health (Postgres, Redis, LLMs)."""
    return system_service.get_system_services(db)
