"""
Event schemas.

Pydantic models for API request validation and response serialization.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class EventBase(BaseModel):
    run_id: str
    event_type: str
    agent: str | None = None
    payload: dict[str, Any] = {}
    cost_usd: float = 0.0
    latency_ms: int = 0


class EventCreate(EventBase):
    pass


class EventResponse(EventBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
