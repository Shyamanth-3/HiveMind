"""
Main API router.

Aggregates all domain-specific routers into a single `api_router`
that gets mounted under the `/api/v1` prefix in main.py.
"""

from fastapi import APIRouter

from app.api.projects import router as projects_router
from app.api.runs import router as runs_router
from app.api.tasks import router as tasks_router
from app.api.events import router as events_router
from app.api.memory import router as memory_router
from app.api.agent_logs import router as agent_logs_router
from app.api.system import router as system_router
from app.api.workflow import router as workflow_router

api_router = APIRouter()

api_router.include_router(projects_router)
api_router.include_router(runs_router)
api_router.include_router(tasks_router)
api_router.include_router(events_router)
api_router.include_router(memory_router)
api_router.include_router(agent_logs_router)
api_router.include_router(system_router)
api_router.include_router(workflow_router)
