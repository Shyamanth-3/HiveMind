"""
Run schemas.

Pydantic models for API request validation and response serialization.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RunStatusLiteral = Literal["running", "completed", "failed"]


class RunBase(BaseModel):
    project_id: str
    goal: str
    status: RunStatusLiteral = "running"
    plan_text: str | None = None
    success_criteria: list[str] = []
    duration_ms: int | None = None


class RunCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    goal: str = Field(min_length=1, max_length=5000)


class RunUpdate(BaseModel):
    status: RunStatusLiteral | None = None
    plan_text: str | None = None
    success_criteria: list[str] | None = None
    duration_ms: int | None = None


class RunResponse(RunBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
