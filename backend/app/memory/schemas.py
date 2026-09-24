"""
Schemas for Agent Memory operations.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator

MIN_CONTENT_CHARS = 10
MAX_CONTENT_CHARS = 500


class MemoryType(str, Enum):
    """Controlled memory classification (also enforced by a DB CHECK constraint)."""
    FACT = "fact"              # "The backend uses PostgreSQL with pgvector."
    DECISION = "decision"      # "Kafka was chosen as the event backbone."
    PREFERENCE = "preference"  # "The project prefers TypeScript."
    CONTEXT = "context"        # constraints / background about the project or goal
    LESSON = "lesson"          # "A run failed because output exceeded the token budget."


class MemoryStoreRequest(BaseModel):
    """Input for storing one durable semantic memory."""
    content: str = Field(description="Standalone statement worth remembering across runs.")
    agent: str = Field(description="The agent storing this memory (ownership).")
    project_id: str = Field(description="Scope: memories are only retrievable within their project.")
    memory_type: MemoryType
    importance: int = Field(default=3, ge=1, le=5)
    run_id: str | None = Field(default=None, description="Provenance: source run.")
    source_event_id: str | None = Field(default=None, description="Provenance: source Kafka event.")
    metadata_: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def _normalise_content(cls, v: str) -> str:
        v = " ".join(v.split())
        if not (MIN_CONTENT_CHARS <= len(v) <= MAX_CONTENT_CHARS):
            raise ValueError(f"content must be {MIN_CONTENT_CHARS}-{MAX_CONTENT_CHARS} chars, got {len(v)}")
        return v


class MemoryStoreResult(BaseModel):
    id: str | None = Field(description="Row id; for a duplicate, the id of the existing memory.")
    created: bool = Field(description="False when the memory was deduplicated.")


class MemorySearchResult(BaseModel):
    """One retrieved memory (the embedding vector is never returned)."""
    id: str
    content: str
    agent: str
    memory_type: MemoryType
    importance: int
    similarity: float
    project_id: str
    run_id: str | None
    created_at: datetime
