"""
Standardized Kafka event envelope schema.
"""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .event_types import EventTypes


class KafkaEvent(BaseModel):
    """
    The standard message envelope for all Kafka events in the system.
    
    Every message published to Kafka must conform to this schema.
    """
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    source: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_json_bytes(self) -> bytes:
        """
        Serialize the event to JSON bytes for Kafka publishing.
        Uses Pydantic's model_dump to handle UUID and datetime serialization natively.
        """
        # model_dump(mode="json") automatically converts UUIDs to strings and datetimes to ISO format strings
        return json.dumps(self.model_dump(mode="json")).encode("utf-8")
