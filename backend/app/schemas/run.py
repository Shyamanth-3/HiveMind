"""
Run schemas.

Pydantic models for API request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class RunBase(BaseModel):
    project_id: str
    goal: str
    status: str = "running"
    plan_text: str | None = None
    success_criteria: list[str] = []
    duration_ms: int | None = None


class RunCreate(BaseModel):
    project_id: str
    goal: str


class RunUpdate(BaseModel):
    status: str | None = None
    plan_text: str | None = None
    success_criteria: list[str] | None = None
    duration_ms: int | None = None


class RunResponse(RunBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
