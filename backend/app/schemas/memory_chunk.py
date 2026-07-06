"""
Memory Chunk schemas.

Pydantic models for API request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class MemoryChunkBase(BaseModel):
    project_id: str
    content: str
    embedding_dimensions: int = 1536
    source: str


class MemoryChunkCreate(MemoryChunkBase):
    pass


class MemoryChunkResponse(MemoryChunkBase):
    id: str
    created_at: datetime
    # similarity_score can be injected at runtime when returning search results
    similarity_score: float | None = None

    model_config = ConfigDict(from_attributes=True)
