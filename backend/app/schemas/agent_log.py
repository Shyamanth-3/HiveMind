"""
Agent Log schemas.

Pydantic models for API request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AgentLogBase(BaseModel):
    run_id: str
    task_id: str
    agent: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    outcome: str
    model: str


class AgentLogCreate(AgentLogBase):
    pass


class AgentLogResponse(AgentLogBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
