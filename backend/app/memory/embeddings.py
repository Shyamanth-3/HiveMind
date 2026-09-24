"""
Embedding service boundary.

The rest of HiveMind only talks to `EmbeddingService` (async, validated, dimension-checked).
Backends are the only place that touches an embedding SDK. Currently: fastembed (local ONNX).
LLM = Groq; embeddings = this module; vector DB = PostgreSQL + pgvector. Three separate concerns.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.metrics import metrics
from app.memory.exceptions import EmbeddingError

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 2000
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class EmbeddingBackend(ABC):
    """Synchronous SDK wrapper: list of texts in, list of vectors out."""

    name: str

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedBackend(EmbeddingBackend):
    """Local ONNX embedding via fastembed. Deterministic, no network after the first model download."""

    def __init__(self, model: str, cache_dir: str):
        from fastembed import TextEmbedding  # heavy import: only when this backend is used

        cache = Path(cache_dir)
        if not cache.is_absolute():
            cache = _BACKEND_DIR / cache
        self.name = f"fastembed:{model}"
        self._model = TextEmbedding(model_name=model, cache_dir=str(cache))

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


class EmbeddingService:
    """Validated, dimension-checked, async embeddings. Never returns a vector of the wrong size."""

    def __init__(self, backend: EmbeddingBackend, dimension: int):
        self.backend = backend
        self.dimension = dimension

    @property
    def description(self) -> str:
        return f"{self.backend.name} ({self.dimension}d)"

    @staticmethod
    def _clean(text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingError("Cannot embed empty text.")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > MAX_INPUT_CHARS:
            raise EmbeddingError(f"Text too long to embed ({len(text)} > {MAX_INPUT_CHARS} chars).")
        return text

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = self.backend.embed_batch(texts)
        except Exception as e:  # provider/SDK errors must be visible, not swallowed
            logger.error("Embedding provider error (%s): %s", self.backend.name, type(e).__name__)
            raise EmbeddingError(f"Embedding provider failed: {e}") from e
        if len(vectors) != len(texts):
            raise EmbeddingError(f"Provider returned {len(vectors)} vectors for {len(texts)} texts.")
        for v in vectors:
            if len(v) != self.dimension:
                raise EmbeddingError(
                    f"Embedding has {len(v)} dimensions, expected {self.dimension} "
                    f"(EMBEDDING_DIMENSION / agent_memories.embedding). Refusing to pad or truncate."
                )
        return vectors

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        cleaned = [self._clean(t) for t in texts]
        try:
            with metrics.timer("embedding_seconds"):
                # CPU-bound: keep the loop free, and never wait on a hung provider longer than EMBEDDING_TIMEOUT_S
                return await asyncio.wait_for(asyncio.to_thread(self._embed_sync, cleaned), settings.EMBEDDING_TIMEOUT_S)
        except asyncio.TimeoutError as e:
            metrics.inc("embedding_timeouts")
            logger.error("Embedding timed out after %.1fs (%s)", settings.EMBEDDING_TIMEOUT_S, self.backend.name)
            raise EmbeddingError(f"Embedding timed out after {settings.EMBEDDING_TIMEOUT_S}s") from e

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]

    def warmup(self) -> None:
        """Load the model and prove it produces vectors of the configured size (fail fast at startup)."""
        self._embed_sync(["warmup"])


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService | None:
    """The process-wide embedding service, or None when EMBEDDING_PROVIDER=none (memory disabled)."""
    name = settings.EMBEDDING_PROVIDER.strip().lower()
    if name in ("", "none"):
        return None
    if name == "fastembed":
        backend = FastEmbedBackend(settings.EMBEDDING_MODEL, settings.EMBEDDING_CACHE_DIR)
        return EmbeddingService(backend, settings.EMBEDDING_DIMENSION)
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER '{name}'. Supported: fastembed, none.")
