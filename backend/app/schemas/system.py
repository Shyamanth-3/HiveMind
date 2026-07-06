"""
System schemas.

Pydantic models for system-level APIs like agent health and services.
These don't map directly to DB tables.
"""

from pydantic import BaseModel


class AgentStatusResponse(BaseModel):
    agent: str
    status: str
    current_task: str | None = None
    last_activity: str
    tasks_completed: int
    success_rate: float


class SystemServiceResponse(BaseModel):
    name: str
    status: str
    latency_ms: int | None = None
    details: str | None = None
