"""
Phase 5 — memory reliability gaps + a recall MEASUREMENT (not a threshold change). Reuses the Phase 2 fixtures.
Recall numbers are printed with `-s`; the test only asserts the production default stays where it is.
"""

import time

import pytest
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.metrics import metrics
from app.memory.embeddings import EmbeddingBackend, EmbeddingError, EmbeddingService
from app.memory.schemas import MemoryType
from app.memory.service import MemoryService
from tests.test_memory import (  # noqa: F401
    DIM, anyio_backend, backend, count, make_project, project_id, real_embeddings, req, service,
    _threshold_for_hashing_backend,
)

pytestmark = pytest.mark.anyio


class HangingBackend(EmbeddingBackend):
    name = "hanging-test"

    def embed_batch(self, texts):
        time.sleep(1.0)
        return [[0.0] * DIM for _ in texts]


async def test_a_hung_embedding_provider_times_out_explicitly(db_session, project_id, monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_TIMEOUT_S", 0.2)
    metrics.reset()
    svc = MemoryService(EmbeddingService(HangingBackend(), DIM))
    started = time.monotonic()
    with pytest.raises(Exception, match="(?i)timed out|cannot"):
        await svc.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event backbone."))
    assert time.monotonic() - started < 0.9  # did not wait for the hung provider
    assert metrics.get("embedding_timeouts") >= 1 and count(db_session) == 0
    with pytest.raises(Exception, match="(?i)timed out|cannot"):
        await svc.retrieve_memories(db_session, "what event backbone do we use?", project_id)


async def test_database_failure_during_retrieval_is_explicit_not_empty(service, db_session, project_id, monkeypatch):
    """A DB error must never look like 'no relevant memories' (that would silently degrade every Queen run)."""
    await service.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event backbone."))

    def boom(*a, **k):
        raise OperationalError("SELECT", {}, Exception("server closed the connection unexpectedly"))

    monkeypatch.setattr(db_session, "execute", boom)
    with pytest.raises(Exception):
        await service.retrieve_memories(db_session, "event backbone", project_id)


# ── recall measurement (real bge-small; skipped when the model is not available offline) ───────────────────────

CORPUS = [
    (MemoryType.DECISION, "The backend stores all application data in PostgreSQL with the pgvector extension."),
    (MemoryType.DECISION, "Agents communicate exclusively through Kafka events, never by direct calls."),
    (MemoryType.CONTEXT, "All LLM calls go through Groq using the openai/gpt-oss-120b model."),
    (MemoryType.FACT, "The frontend is a Next.js application using the App Router and TypeScript."),
    (MemoryType.PREFERENCE, "The team prefers small pull requests with exhaustive automated tests."),
]
# (query, index of the memory that should be recalled, category)
QUERIES = [
    ("Where is our data persisted?", 0, "paraphrase"),
    ("How do the agents talk to each other?", 1, "paraphrase"),
    ("Which language model provider do we call?", 2, "paraphrase"),
    ("What did we build the UI with?", 3, "paraphrase"),
    ("How should pull requests be sized?", 4, "paraphrase"),
]
UNRELATED = ["What is the best recipe for chocolate cake?", "Who won the football world cup in 2010?"]


async def test_recall_benchmark_with_the_production_threshold(real_embeddings, db_session, project_id):
    svc = MemoryService(embedding_service=real_embeddings)
    for mtype, text in CORPUS:
        await svc.store_memory(db_session, req(project_id, text, mtype))
    hits = top1 = 0
    rows = []
    for q, want, cat in QUERIES:
        got = await svc.retrieve_memories(db_session, q, project_id, top_k=3)
        texts = [g.content for g in got]
        rows.append((cat, q, [round(g.similarity, 2) for g in got]))
        hits += CORPUS[want][1] in texts
        top1 += bool(texts) and texts[0] == CORPUS[want][1]
    false_pos = 0
    for q in UNRELATED:
        got = await svc.retrieve_memories(db_session, q, project_id, top_k=3)
        false_pos += len(got)
        rows.append(("unrelated", q, [round(g.similarity, 2) for g in got]))
    n = len(QUERIES)
    print(f"\nMEMORY_MIN_SIMILARITY={settings.MEMORY_MIN_SIMILARITY} recall@3={hits}/{n} top1={top1}/{n} "
          f"unrelated_returned={false_pos}/{len(UNRELATED)}")
    for r in rows:
        print("  ", r)
    assert settings.MEMORY_MIN_SIMILARITY >= 0.3  # measurement only: the threshold is never lowered to pass
    assert false_pos == 0  # the threshold must keep irrelevant memory out of the prompt
