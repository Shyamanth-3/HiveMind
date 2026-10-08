"""
Project schemas.

Pydantic models for API request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str
    owner: str
    goal_summary: str


class ProjectCreate(ProjectBase):
    name: str = Field(min_length=1, max_length=255)
    owner: str = Field(min_length=1, max_length=100)
    goal_summary: str = Field(min_length=1, max_length=5000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    owner: str | None = Field(default=None, min_length=1, max_length=100)
    goal_summary: str | None = Field(default=None, min_length=1, max_length=5000)


class ProjectResponse(ProjectBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
