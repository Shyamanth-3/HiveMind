"""
Semantic memory service: store and retrieve durable, project-scoped memories.

  store_memory:     validate -> secret check -> exact dedup -> embed -> semantic dedup -> insert (one txn)
  retrieve_memories: embed query -> pgvector cosine search (project scope, filters) -> threshold -> top-K

Failure policy: nothing is swallowed. Embedding, database and pgvector errors raise
(MemoryStoreError / MemorySearchError), so a caller can never believe a memory was stored/read when
it was not. An empty result is not an error. Logs never contain memory text or vectors.
"""

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import metrics
from app.memory.embeddings import EmbeddingService, get_embedding_service
from app.memory.exceptions import EmbeddingError, MemorySearchError, MemorySecretError, MemoryStoreError
from app.memory.schemas import MemorySearchResult, MemoryStoreRequest, MemoryStoreResult, MemoryType
from app.memory.security import find_secret
from app.models.agent_memory import AgentMemory

logger = logging.getLogger(__name__)


def content_hash(content: str) -> str:
    """Stable hash of normalised content (case/whitespace-insensitive) for exact dedup."""
    return hashlib.sha256(" ".join(content.lower().split()).encode("utf-8")).hexdigest()


class MemoryService:
    def __init__(self, embedding_service: EmbeddingService | None = None):
        # None => memory disabled (EMBEDDING_PROVIDER=none). Callers must check `enabled`.
        self.embedding_service = embedding_service or get_embedding_service()

    @property
    def enabled(self) -> bool:
        return self.embedding_service is not None

    # ── store ───────────────────────────────────────────────────────────

    async def store_memory(self, db: Session, request: MemoryStoreRequest) -> MemoryStoreResult:
        if not self.enabled:
            raise MemoryStoreError("Memory is disabled (EMBEDDING_PROVIDER=none)")

        if (label := find_secret(request.content)) is not None:
            logger.warning("Memory rejected: content looks like a secret (%s)", label)
            raise MemorySecretError(f"Refusing to store memory that looks like a secret ({label}).")

        chash = content_hash(request.content)
        mtype = request.memory_type.value
        try:
            existing = db.scalar(select(AgentMemory.id).where(
                AgentMemory.project_id == request.project_id,
                AgentMemory.memory_type == mtype,
                AgentMemory.content_hash == chash,
            ))
            if existing:
                logger.info("Memory deduplicated (exact): type=%s", mtype)
                return MemoryStoreResult(id=existing, created=False)

            try:
                vector = await self.embedding_service.embed_text(request.content)
            except EmbeddingError as e:
                raise MemoryStoreError(f"Embedding failed, memory NOT stored: {e}") from e

            near = db.execute(
                select(AgentMemory.id, AgentMemory.embedding.cosine_distance(vector).label("d"))
                .where(AgentMemory.project_id == request.project_id, AgentMemory.memory_type == mtype)
                .order_by("d").limit(1)
            ).first()
            if near is not None and (1.0 - near.d) >= settings.MEMORY_DEDUP_SIMILARITY:
                logger.info("Memory deduplicated (semantic, similarity=%.3f): type=%s", 1.0 - near.d, mtype)
                return MemoryStoreResult(id=near.id, created=False)

            stmt = (
                pg_insert(AgentMemory)
                .values(
                    project_id=request.project_id, run_id=request.run_id,
                    source_event_id=request.source_event_id, agent=request.agent,
                    memory_type=mtype, importance=request.importance, content=request.content,
                    content_hash=chash, embedding=vector, metadata_=request.metadata_,
                )
                .on_conflict_do_nothing(index_elements=["project_id", "memory_type", "content_hash"])
                .returning(AgentMemory.id)
            )
            new_id = db.execute(stmt).scalar()
            db.commit()
            if new_id is None:  # lost a race with a concurrent identical insert
                logger.info("Memory deduplicated (concurrent): type=%s", mtype)
                return MemoryStoreResult(id=None, created=False)
            logger.info("Memory stored: type=%s importance=%d | run=%s", mtype, request.importance, request.run_id)
            return MemoryStoreResult(id=new_id, created=True)
        except MemoryStoreError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error("Memory persistence error: %s", type(e).__name__)
            raise MemoryStoreError(f"Failed to store memory: {e}") from e

    # ── retrieve ────────────────────────────────────────────────────────

    async def retrieve_memories(
        self,
        db: Session,
        query: str,
        project_id: str,
        top_k: int | None = None,
        min_similarity: float | None = None,
        memory_types: list[MemoryType] | None = None,
        agent: str | None = None,
        run_id: str | None = None,  # correlation only (logs); never used for filtering
    ) -> list[MemorySearchResult]:
        if not self.enabled:
            raise MemorySearchError("Memory is disabled (EMBEDDING_PROVIDER=none)")
        if not query or not query.strip():
            return []
        top_k = top_k or settings.MEMORY_TOP_K
        threshold = settings.MEMORY_MIN_SIMILARITY if min_similarity is None else min_similarity

        logger.info("Memory retrieval started | run=%s project=%s", run_id, project_id)
        try:
            vector = await self.embedding_service.embed_text(query)
        except EmbeddingError as e:
            raise MemorySearchError(f"Embedding failed, cannot search memory: {e}") from e

        try:
            distance = AgentMemory.embedding.cosine_distance(vector).label("distance")
            stmt = select(AgentMemory, distance).where(
                AgentMemory.project_id == project_id,        # scope: never cross projects
                distance <= 1.0 - threshold,                 # similarity threshold
            )
            if memory_types:
                stmt = stmt.where(AgentMemory.memory_type.in_([t.value for t in memory_types]))
            if agent:
                stmt = stmt.where(AgentMemory.agent == agent)
            with metrics.timer("memory_retrieval_seconds"):
                rows = db.execute(stmt.order_by("distance", AgentMemory.importance.desc()).limit(top_k)).all()
        except Exception as e:
            db.rollback()
            logger.error("Memory retrieval error: %s", type(e).__name__)
            raise MemorySearchError(f"Semantic search failed: {e}") from e

        results = [
            MemorySearchResult(
                id=m.id, content=m.content, agent=m.agent, memory_type=MemoryType(m.memory_type),
                importance=m.importance, similarity=round(1.0 - d, 4), project_id=m.project_id,
                run_id=m.run_id, created_at=m.created_at,
            )
            for m, d in rows
        ]
        if results:
            logger.info("Memory retrieval completed: %d results (best similarity %.3f) | run=%s", len(results), results[0].similarity, run_id)
        else:
            logger.info("No relevant memories found | run=%s", run_id)
        return results
