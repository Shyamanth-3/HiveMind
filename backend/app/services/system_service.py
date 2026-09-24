"""
System service.

Provides system-level data like agent health and infrastructure status.
Currently mocks agent status since real-time WebSocket agent tracking
is a future phase.
"""

from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.system import AgentStatusResponse, SystemServiceResponse
from app.core.config import settings
from app.db.database import engine

# Mocked agent status matching the frontend's mockData.ts
MOCK_AGENT_STATUSES = [
    {
        "agent": "ceo_agent",
        "status": "idle",
        "current_task": None,
        "last_activity": "2026-06-21T14:20:02Z",
        "tasks_completed": 3,
        "success_rate": 100.0,
    },
    {
        "agent": "pm_agent",
        "status": "idle",
        "current_task": None,
        "last_activity": "2026-06-21T14:20:03Z",
        "tasks_completed": 3,
        "success_rate": 100.0,
    },
    {
        "agent": "research_agent",
        "status": "online",
        "current_task": None,
        "last_activity": "2026-06-21T14:20:08Z",
        "tasks_completed": 3,
        "success_rate": 100.0,
    },
    {
        "agent": "developer_agent",
        "status": "working",
        "current_task": "Building dental clinic landing page",
        "last_activity": "2026-06-21T14:22:00Z",
        "tasks_completed": 3,
        "success_rate": 87.5,
    },
    {
        "agent": "reviewer_qa_agent",
        "status": "idle",
        "current_task": None,
        "last_activity": "2026-06-21T08:01:00Z",
        "tasks_completed": 3,
        "success_rate": 100.0,
    },
]


def get_agent_statuses() -> list[AgentStatusResponse]:
    """Retrieve current status of all agents."""
    return [AgentStatusResponse(**data) for data in MOCK_AGENT_STATUSES]


def get_system_services(db: Session) -> list[SystemServiceResponse]:
    """Check infrastructure health (Postgres, Redis, LLM)."""
    
    # Check Postgres
    try:
        # Simple query to check if DB is responsive
        db.execute(text("SELECT 1"))
        pg_status = "online"
        pg_details = "Connected via SQLAlchemy"
    except Exception as e:
        pg_status = "offline"
        pg_details = str(e)
        
    services = [
        SystemServiceResponse(
            name="PostgreSQL",
            status=pg_status,
            latency_ms=24,  # Hardcoded mock for now
            details=pg_details,
        ),
        SystemServiceResponse(
            name="Redis",
            status="online",
            latency_ms=8,
            details=f"Connected to {settings.REDIS_URL.split('://')[0]}",
        ),
        SystemServiceResponse(
            name="LLM Provider",
            status="cold-start",
            latency_ms=2400,
            details=f"{settings.LLM_PROVIDER} · {settings.LLM_MODEL or 'default model'}",
        ),
    ]
    return services
