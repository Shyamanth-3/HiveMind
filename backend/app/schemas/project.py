"""
Project schemas.

Pydantic models for API request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ProjectBase(BaseModel):
    name: str
    owner: str
    goal_summary: str


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = None
    owner: str | None = None
    goal_summary: str | None = None


class ProjectResponse(ProjectBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
