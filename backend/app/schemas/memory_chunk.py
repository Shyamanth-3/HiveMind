"""
Memory Chunk schemas.

Pydantic models for API request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class MemoryChunkBase(BaseModel):
    project_id: str
    content: str
    embedding_dimensions: int = 1536
    source: str


class MemoryChunkCreate(MemoryChunkBase):
    project_id: str = Field(min_length=1, max_length=36)
    content: str = Field(min_length=1, max_length=5000)
    embedding_dimensions: int = Field(default=1536, ge=1, le=4096)
    source: str = Field(min_length=1, max_length=100)


class MemoryChunkResponse(MemoryChunkBase):
    id: str
    created_at: datetime
    # similarity_score can be injected at runtime when returning search results
    similarity_score: float | None = None

    model_config = ConfigDict(from_attributes=True)
