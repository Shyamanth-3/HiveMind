"""
Task schemas.

Pydantic models for API request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TaskBase(BaseModel):
    run_id: str
    type: str
    assigned_agent: str
    depends_on: list[str] = []
    status: str = "pending"
    result: str | None = None
    retry_count: int = 0


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    status: str | None = None
    result: str | None = None
    retry_count: int | None = None


class TaskResponse(TaskBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
