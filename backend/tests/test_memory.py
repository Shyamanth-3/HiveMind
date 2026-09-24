"""
Phase 2 semantic memory tests: embeddings, storage, retrieval, scope, dedup, secrets, Queen
integration, persistence. Real PostgreSQL + pgvector; no SQLite, no Groq calls.

Two embedding backends:
  * HashingBackend: deterministic bag-of-words vectors (texts sharing words are similar) for logic tests.
  * the real local model (BAAI/bge-small-en-v1.5 via fastembed) for semantic-quality tests; those tests
    are skipped if the model cannot be loaded (first run needs a one-time download).
"""

import hashlib
import logging
import math
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text

from agents.queen.schemas import Strategy
from agents.queen.workflow import QueenWorkflow
from app.core.config import settings
from app.memory import embeddings as emb
from app.memory.embeddings import EmbeddingBackend, EmbeddingService, get_embedding_service
from app.memory.exceptions import (
    EmbeddingError, MemorySearchError, MemorySecretError, MemoryStoreError,
)
from app.memory.extraction import MemoryCandidate, MemoryExtraction, sanitize_candidates
from app.memory.formatting import NO_MEMORIES, format_memory_context
from app.memory.schemas import MemoryStoreRequest, MemoryType
from app.memory.security import find_secret
from app.memory.service import MemoryService, content_hash
from app.models import AgentMemory, Project, Run
from tests.fakes import REPLIES, ScriptedLLM

pytestmark = pytest.mark.anyio
DIM = settings.EMBEDDING_DIMENSION


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── backends ────────────────────────────────────────────────────────────


class HashingBackend(EmbeddingBackend):
    """Bag-of-words hashing into DIM dims, L2-normalised. Deterministic, offline."""

    name = "hashing-test"

    def __init__(self, dim: int = DIM):
        self.dim, self.calls = dim, 0

    def embed_batch(self, texts):
        self.calls += 1
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for w in {w.strip(".,!?").lower() for w in t.split()}:
                if len(w) > 2:
                    v[int(hashlib.sha256(w.encode()).hexdigest(), 16) % self.dim] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class FailingBackend(EmbeddingBackend):
    name = "failing-test"

    def embed_batch(self, texts):
        raise RuntimeError("401 unauthorized")


@pytest.fixture(autouse=True)
def _threshold_for_hashing_backend(request, monkeypatch):
    """Bag-of-words cosine is lower than bge's for the same pair, so relax the threshold for those tests.
    Tests that use the real model (real_embeddings) keep the production default."""
    if "real_embeddings" not in request.fixturenames:
        monkeypatch.setattr(settings, "MEMORY_MIN_SIMILARITY", 0.5)


@pytest.fixture
def backend():
    return HashingBackend()


@pytest.fixture
def service(backend):
    return MemoryService(embedding_service=EmbeddingService(backend, DIM))


@pytest.fixture(scope="session")
def real_embeddings():
    try:
        svc = EmbeddingService(emb.FastEmbedBackend(settings.EMBEDDING_MODEL, settings.EMBEDDING_CACHE_DIR), DIM)
        svc.warmup()
    except Exception as e:  # no model files and no network
        pytest.skip(f"local embedding model unavailable: {e}")
    return svc


# ── data helpers ────────────────────────────────────────────────────────


def make_project(db, name="p"):
    p = Project(name=name, owner="o", goal_summary="g")
    db.add(p)
    db.flush()
    return p.id


def make_run(db, project_id, goal="goal"):
    r = Run(project_id=project_id, goal=goal)
    db.add(r)
    db.commit()
    return r.id


@pytest.fixture
def project_id(db_session):
    pid = make_project(db_session)
    db_session.commit()
    return pid


def req(project_id, content, mtype=MemoryType.FACT, **kw):
    return MemoryStoreRequest(content=content, agent="queen", project_id=project_id, memory_type=mtype, **kw)


def count(db, project_id=None):
    q = select(func.count()).select_from(AgentMemory)
    if project_id:
        q = q.where(AgentMemory.project_id == project_id)
    return db.scalar(q)


# ══ embeddings ══════════════════════════════════════════════════════════


async def test_embedding_service_returns_vectors_of_the_configured_dimension(backend):
    svc = EmbeddingService(backend, DIM)
    v = await svc.embed_text("HiveMind uses Kafka")
    assert len(v) == DIM and svc.dimension == DIM and "hashing-test" in svc.description
    many = await svc.embed_texts(["one two three", "four five six"])
    assert [len(x) for x in many] == [DIM, DIM] and backend.calls == 2 and await svc.embed_texts([]) == []


async def test_embedding_texts_are_sent_to_the_backend_as_one_batch(backend):
    await EmbeddingService(backend, DIM).embed_texts(["aaa bbb", "ccc ddd", "eee fff"])
    assert backend.calls == 1


@pytest.mark.parametrize("bad", ["", "   ", "\n\t", None, 123, "x" * 2001])
async def test_embedding_rejects_invalid_input_without_calling_the_provider(backend, bad):
    with pytest.raises(EmbeddingError):
        await EmbeddingService(backend, DIM).embed_text(bad)
    assert backend.calls == 0


async def test_embedding_provider_failure_is_raised_as_embedding_error():
    with pytest.raises(EmbeddingError, match="provider failed"):
        await EmbeddingService(FailingBackend(), DIM).embed_text("hello world")


async def test_embedding_wrong_dimension_is_rejected_never_padded_or_truncated():
    with pytest.raises(EmbeddingError, match="dimensions"):
        await EmbeddingService(HashingBackend(dim=DIM - 1), DIM).embed_text("hello world")


def test_embedding_factory_none_and_unsupported(monkeypatch):
    get_embedding_service.cache_clear()
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "none")
    assert get_embedding_service() is None and MemoryService().enabled is False
    get_embedding_service.cache_clear()
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "featherless")
    with pytest.raises(ValueError, match="Supported: fastembed, none"):
        get_embedding_service()
    get_embedding_service.cache_clear()


async def test_real_model_dimension_norm_and_determinism(real_embeddings):
    a = await real_embeddings.embed_text("HiveMind uses PostgreSQL with pgvector.")
    b = await real_embeddings.embed_text("HiveMind uses PostgreSQL with pgvector.")
    assert len(a) == 384 == DIM and a == b
    assert abs(math.sqrt(sum(x * x for x in a)) - 1.0) < 1e-3
    assert "fastembed:BAAI/bge-small-en-v1.5" in real_embeddings.description


# ══ database / pgvector ═════════════════════════════════════════════════


def test_database_vector_dimension_matches_configuration(db_session):
    typmod = db_session.scalar(text(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'agent_memories'::regclass AND attname = 'embedding'"))
    assert typmod == DIM == 384


async def test_stored_vector_is_persisted_with_full_dimension_and_provenance(service, db_session, project_id):
    run_id = make_run(db_session, project_id)
    res = await service.store_memory(db_session, req(
        project_id, "The backend uses PostgreSQL with pgvector.", MemoryType.FACT,
        importance=4, run_id=run_id, source_event_id="evt-1"))
    assert res.created and res.id
    db_session.expire_all()
    m = db_session.get(AgentMemory, res.id)
    assert len(m.embedding) == DIM and m.memory_type == "fact" and m.importance == 4
    assert (m.project_id, m.run_id, m.source_event_id, m.agent) == (project_id, run_id, "evt-1", "queen")
    assert m.content_hash == content_hash(m.content) and m.created_at is not None


async def test_hnsw_index_and_cosine_operator_are_used_by_pgvector(service, db_session, project_id):
    await service.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event backbone."))
    vec = "[" + ",".join(["0.1"] * DIM) + "]"
    db_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(r[0] for r in db_session.execute(text(
        f"EXPLAIN SELECT id FROM agent_memories ORDER BY embedding <=> '{vec}'::vector LIMIT 5")))
    assert "ix_agent_memories_embedding_hnsw" in plan
    db_session.rollback()


# ══ storage ═════════════════════════════════════════════════════════════


async def test_exact_duplicates_are_not_stored_twice_and_skip_embedding(service, backend, db_session, project_id):
    first = await service.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event backbone."))
    calls = backend.calls
    for variant in ("hivemind uses kafka as its event backbone.", "  HiveMind   uses Kafka as its\nevent backbone. "):
        again = await service.store_memory(db_session, req(project_id, variant))
        assert again.created is False and again.id == first.id
    assert count(db_session) == 1 and backend.calls == calls  # exact dup detected before embedding


async def test_near_duplicate_is_deduplicated_semantically(service, db_session, project_id):
    base = "The expense tracker uses React Node Postgres Redis Docker Kubernetes Terraform Grafana Prometheus Jest"
    a = await service.store_memory(db_session, req(project_id, base))
    b = await service.store_memory(db_session, req(project_id, base + " Cypress"))
    assert a.created and b.created is False and b.id == a.id and count(db_session) == 1


async def test_conflicting_memories_are_both_kept_with_provenance(service, db_session, project_id):
    """Policy: no supersede logic. 'Redis' vs 'Kafka' are different memories; both are retained."""
    r1, r2 = make_run(db_session, project_id), make_run(db_session, project_id)
    a = await service.store_memory(db_session, req(project_id, "HiveMind uses Redis as its event bus.", run_id=r1))
    b = await service.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event bus.", run_id=r2))
    assert a.created and b.created and count(db_session) == 2
    assert {m.run_id for m in db_session.scalars(select(AgentMemory))} == {r1, r2}


async def test_same_text_is_kept_per_type_and_per_project(service, db_session, project_id):
    other = make_project(db_session, "other")
    db_session.commit()
    text_ = "Everything is written in TypeScript."
    results = [
        await service.store_memory(db_session, req(project_id, text_, MemoryType.FACT)),
        await service.store_memory(db_session, req(project_id, text_, MemoryType.PREFERENCE)),
        await service.store_memory(db_session, req(other, text_, MemoryType.FACT)),
    ]
    assert all(r.created for r in results) and count(db_session) == 3


async def test_embedding_failure_never_reports_success_and_stores_nothing(db_session, project_id):
    svc = MemoryService(embedding_service=EmbeddingService(FailingBackend(), DIM))
    with pytest.raises(MemoryStoreError, match="NOT stored"):
        await svc.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event backbone."))
    assert count(db_session) == 0


async def test_database_failure_rolls_back_and_is_visible(service, db_session, project_id):
    with pytest.raises(MemoryStoreError):
        await service.store_memory(db_session, req("no-such-project", "HiveMind uses Kafka as its event backbone."))
    assert count(db_session) == 0
    ok = await service.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event backbone."))
    assert ok.created  # session is usable after the rollback


@pytest.mark.parametrize("kwargs", [
    dict(content="short"), dict(content="x" * 501), dict(content="A perfectly fine memory", importance=9),
    dict(content="A perfectly fine memory", importance=0), dict(content="A perfectly fine memory", memory_type="opinion"),
])
def test_store_request_validation(kwargs):
    base = dict(content="A perfectly fine memory", agent="queen", project_id="p", memory_type="fact")
    with pytest.raises(ValidationError):
        MemoryStoreRequest(**{**base, **kwargs})


def test_db_rejects_uncontrolled_memory_types(db_session, project_id):
    with pytest.raises(Exception, match="ck_agent_memories_type"):
        db_session.execute(text(
            "INSERT INTO agent_memories (id, project_id, agent, memory_type, content, content_hash, embedding, "
            "metadata_, created_at, updated_at) VALUES ('m1', :p, 'q', 'gossip', 'x', 'h', "
            f"'[{','.join(['0.1'] * DIM)}]', '{{}}', now(), now())"), {"p": project_id})
    db_session.rollback()


async def test_disabled_memory_refuses_to_store_or_search(db_session, project_id):
    off = MemoryService(embedding_service=None)
    if off.enabled:  # MemoryService() falls back to the configured provider; tests configure "none"
        pytest.skip("EMBEDDING_PROVIDER is configured")
    with pytest.raises(MemoryStoreError, match="disabled"):
        await off.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event backbone."))
    with pytest.raises(MemorySearchError, match="disabled"):
        await off.retrieve_memories(db_session, "kafka", project_id)


# ══ retrieval ═══════════════════════════════════════════════════════════


async def seed(service, db, project_id):
    for content, mtype, imp in [
        ("HiveMind uses PostgreSQL with pgvector as its database.", MemoryType.FACT, 4),
        ("HiveMind uses Kafka as its event backbone.", MemoryType.DECISION, 5),
        ("The frontend prefers TypeScript over plain JavaScript.", MemoryType.PREFERENCE, 3),
    ]:
        await service.store_memory(db, req(project_id, content, mtype, importance=imp))


async def test_semantic_match_ranks_the_relevant_memory_first(service, db_session, project_id):
    await seed(service, db_session, project_id)
    res = await service.retrieve_memories(db_session, "which database does HiveMind use with pgvector", project_id)
    assert res and "PostgreSQL" in res[0].content and res[0].memory_type is MemoryType.FACT
    assert all(0.0 <= r.similarity <= 1.0 for r in res)
    assert [r.similarity for r in res] == sorted((r.similarity for r in res), reverse=True)
    assert not hasattr(res[0], "embedding")  # vectors never leave the service


async def test_irrelevant_memories_are_filtered_by_the_similarity_threshold(service, db_session, project_id):
    await seed(service, db_session, project_id)
    assert await service.retrieve_memories(db_session, "bakery ordering menu photography", project_id) == []
    lowered = await service.retrieve_memories(db_session, "bakery ordering menu photography", project_id,
                                              min_similarity=-1.0)
    assert len(lowered) == 3  # threshold is what filtered them


async def test_top_k_limits_results(service, db_session, project_id):
    await seed(service, db_session, project_id)
    q = "HiveMind uses PostgreSQL Kafka TypeScript"
    assert len(await service.retrieve_memories(db_session, q, project_id, top_k=2, min_similarity=0.0)) == 2
    assert len(await service.retrieve_memories(db_session, q, project_id, top_k=1, min_similarity=0.0)) == 1


async def test_memory_type_and_agent_filters(service, db_session, project_id):
    await seed(service, db_session, project_id)
    q = "HiveMind uses PostgreSQL Kafka TypeScript"
    only = await service.retrieve_memories(db_session, q, project_id, min_similarity=0.0,
                                           memory_types=[MemoryType.DECISION])
    assert [r.memory_type for r in only] == [MemoryType.DECISION]
    assert await service.retrieve_memories(db_session, q, project_id, min_similarity=0.0, agent="architect") == []


async def test_projects_cannot_read_each_others_memories(service, db_session, project_id):
    other = make_project(db_session, "other")
    db_session.commit()
    await seed(service, db_session, project_id)
    q = "which database does HiveMind use with pgvector"
    assert await service.retrieve_memories(db_session, q, other, min_similarity=0.0) == []
    assert len(await service.retrieve_memories(db_session, q, project_id, min_similarity=0.0)) >= 1


async def test_empty_memory_and_empty_query_are_not_errors(service, db_session, project_id):
    assert await service.retrieve_memories(db_session, "anything at all", project_id) == []
    assert await service.retrieve_memories(db_session, "   ", project_id) == []


async def test_retrieval_fails_clearly_on_embedding_or_pgvector_errors(service, db_session, project_id, monkeypatch):
    bad = MemoryService(embedding_service=EmbeddingService(FailingBackend(), DIM))
    with pytest.raises(MemorySearchError, match="cannot search"):
        await bad.retrieve_memories(db_session, "kafka", project_id)

    def boom(*a, **k):
        raise RuntimeError("pgvector exploded")

    monkeypatch.setattr(db_session, "execute", boom)
    with pytest.raises(MemorySearchError, match="Semantic search failed"):
        await service.retrieve_memories(db_session, "kafka events", project_id)


async def test_memory_survives_service_recreation_and_new_sessions(session_factory, backend, project_id):
    """Persistence: store with one service/session, then a brand-new service + session still finds it."""
    with session_factory() as db1:
        await MemoryService(EmbeddingService(HashingBackend(), DIM)).store_memory(
            db1, req(project_id, "HiveMind uses Kafka as its event backbone.", MemoryType.DECISION))
    fresh = MemoryService(EmbeddingService(HashingBackend(), DIM))
    with session_factory() as db2:
        res = await fresh.retrieve_memories(db2, "what is the HiveMind event backbone", project_id)
    assert [r.content for r in res] == ["HiveMind uses Kafka as its event backbone."]


# ══ real embedding model: semantic quality ══════════════════════════════


async def test_real_model_spec_example_only_the_relevant_memory_is_returned(real_embeddings, db_session, project_id):
    svc = MemoryService(embedding_service=real_embeddings)
    await svc.store_memory(db_session, req(project_id, "HiveMind uses PostgreSQL with pgvector."))
    await svc.store_memory(db_session, req(project_id, "Previous run generated five Builder tasks.", MemoryType.CONTEXT))
    res = await svc.retrieve_memories(db_session, "What database does HiveMind use?", project_id)
    assert [r.content for r in res] == ["HiveMind uses PostgreSQL with pgvector."]
    assert res[0].similarity >= settings.MEMORY_MIN_SIMILARITY


async def test_real_model_paraphrase_and_unrelated_query(real_embeddings, db_session, project_id):
    svc = MemoryService(embedding_service=real_embeddings)
    await svc.store_memory(db_session, req(project_id, "The user prefers TypeScript for the frontend.",
                                           MemoryType.PREFERENCE))
    hit = await svc.retrieve_memories(db_session, "Which language should the frontend be written in?", project_id)
    assert len(hit) == 1 and hit[0].memory_type is MemoryType.PREFERENCE
    assert await svc.retrieve_memories(db_session, "Plan a bakery website with an online ordering menu", project_id) == []


async def test_real_model_dedups_a_reworded_memory_but_keeps_a_different_one(real_embeddings, db_session, project_id):
    svc = MemoryService(embedding_service=real_embeddings)
    a = await svc.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event backbone."))
    b = await svc.store_memory(db_session, req(project_id, "HiveMind uses Kafka as its event backbone!"))
    c = await svc.store_memory(db_session, req(project_id, "HiveMind stores vectors in PostgreSQL with pgvector."))
    assert a.created and b.created is False and c.created and count(db_session) == 2


# ══ security ════════════════════════════════════════════════════════════

SECRETS = [
    "The Groq key is gsk_abcdefghijklmnopqrstuvwxyz0123456789",
    "Use sk-proj-abcdefghijklmnopqrstuvwx for the API",
    "GitHub token ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "AWS key AKIAABCDEFGHIJKLMNOP is used",
    "Send header Authorization: Bearer abcdef123456",
    "The password is hunter2hunter2",
    "api_key=abcd1234efgh5678",
    "DATABASE_URL is postgresql://admin:s3cretpass@db.internal:5432/app",
    "-----BEGIN RSA PRIVATE KEY----- MIIEow",
    "token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    "secret = 9f8a7b6c5d4e3f2a1b0c",
]
BENIGN = [
    "HiveMind uses Kafka as its event backbone.",
    "The API uses a token bucket rate limiter.",
    "Passwords are hashed with argon2 before storage.",
    "The team prefers TypeScript and PostgreSQL.",
]


@pytest.mark.parametrize("secret", SECRETS)
async def test_secrets_are_detected_and_never_stored(secret, service, db_session, project_id):
    assert find_secret(secret) is not None
    with pytest.raises(MemorySecretError):
        await service.store_memory(db_session, req(project_id, secret))
    assert count(db_session) == 0


@pytest.mark.parametrize("ok", BENIGN)
def test_ordinary_statements_are_not_flagged_as_secrets(ok):
    assert find_secret(ok) is None


def test_extraction_guardrails_are_deterministic():
    ext = MemoryExtraction(memories=[
        MemoryCandidate(memory_type="decision", content="Kafka is the event backbone of the project.", importance=5),
        MemoryCandidate(memory_type="Decision", content="kafka is the event backbone of the project.", importance=2),   # dup
        MemoryCandidate(memory_type="gossip", content="Something the model invented entirely.", importance=3),         # type
        MemoryCandidate(memory_type="fact", content="short", importance=3),                                           # length
        MemoryCandidate(memory_type="fact", content="Use api_key=abcd1234efgh5678 for access", importance=3),          # secret
        MemoryCandidate(memory_type="fact", content="A valid fact about the project database.", importance=9),        # importance
        MemoryCandidate(memory_type="preference", content="The team prefers TypeScript everywhere.", importance=4),
        MemoryCandidate(memory_type="lesson", content="Structured output must be validated before use.", importance=3),
        MemoryCandidate(memory_type="context", content="The project targets small businesses initially.", importance=1),
    ])
    kept = sanitize_candidates(ext, max_items=3)
    assert [(t.value, i) for t, _, i in kept] == [("decision", 5), ("preference", 4), ("lesson", 3)]
    assert sanitize_candidates(ext, 3) == kept  # same input, same output


def test_memory_context_formatting_is_deterministic_and_hides_internals(db_session):
    from app.memory.schemas import MemorySearchResult
    from datetime import datetime, timezone
    mk = lambda c, t: MemorySearchResult(id="mem_secret_id", content=c, agent="queen", memory_type=t, importance=3,
                                         similarity=0.91, project_id="p", run_id=None,
                                         created_at=datetime.now(timezone.utc))
    out = format_memory_context([mk("Kafka is the backbone.", MemoryType.DECISION), mk("Uses pgvector.", MemoryType.FACT)])
    assert out == "Relevant HiveMind Memory:\n1. [decision] Kafka is the backbone.\n2. [fact] Uses pgvector."
    assert "mem_secret_id" not in out and "0.91" not in out
    assert format_memory_context([]) == NO_MEMORIES == "Relevant HiveMind Memory:\nNo relevant memories found."


# ══ Queen integration ═══════════════════════════════════════════════════


def queen_wf(llm, service):
    return QueenWorkflow(llm=llm, memory_service=service, timeout=30)


async def run_queen(wf, run_id, goal, project_id, event_id="evt-queen-1"):
    return await wf.run(workflow_run_id=run_id, goal=goal, project_id=project_id, source_event_id=event_id)


def strategy_prompt(llm):
    return next(p for p in llm.prompts if "Project Goal" in p and "Context from analysis" in p)


def extraction(*items):
    return dict(REPLIES, MemoryExtraction={"memories": [
        {"memory_type": t, "content": c, "importance": i} for t, c, i in items]})


async def test_queen_with_empty_memory_db_continues_normally(service, db_session, project_id):
    run_id = make_run(db_session, project_id)
    llm = ScriptedLLM(dict(REPLIES))
    strategy = await run_queen(queen_wf(llm, service), run_id, "Build an expense tracker", project_id)
    assert isinstance(strategy, Strategy)
    assert "No relevant memories found." in strategy_prompt(llm) and count(db_session) == 0


async def test_queen_retrieves_relevant_memory_into_its_prompt_and_excludes_others(service, db_session, project_id):
    other = make_project(db_session, "other")
    db_session.commit()
    await service.store_memory(db_session, req(project_id, "The expense tracker uses PostgreSQL as its only database.",
                                               MemoryType.DECISION))
    await service.store_memory(db_session, req(project_id, "Bakery photography needs warm colors.", MemoryType.CONTEXT))
    await service.store_memory(db_session, req(other, "The expense tracker uses MongoDB as its only database.",
                                               MemoryType.DECISION))
    run_id = make_run(db_session, project_id)
    llm = ScriptedLLM(dict(REPLIES))
    await run_queen(queen_wf(llm, service), run_id, "Design the expense tracker database", project_id)
    p = strategy_prompt(llm)
    assert "Relevant HiveMind Memory:\n1. [decision] The expense tracker uses PostgreSQL as its only database." in p
    assert "Bakery" not in p and "MongoDB" not in p  # irrelevant + other project's memory excluded
    assert "mem_" not in p


async def test_queen_stores_only_extracted_durable_memories_with_provenance(service, db_session, project_id):
    run_id = make_run(db_session, project_id)
    llm = ScriptedLLM(extraction(
        ("decision", "The expense tracker stores data in PostgreSQL.", 5),
        ("preference", "The team prefers TypeScript for the frontend.", 3),
    ))
    strategy = await run_queen(queen_wf(llm, service), run_id, "Build an expense tracker", project_id, "evt-9")
    db_session.expire_all()
    rows = db_session.scalars(select(AgentMemory).order_by(AgentMemory.importance.desc())).all()
    assert [(r.memory_type, r.agent, r.run_id, r.source_event_id, r.project_id) for r in rows] == [
        ("decision", "queen", run_id, "evt-9", project_id), ("preference", "queen", run_id, "evt-9", project_id)]
    stored = " ".join(r.content for r in rows)
    assert not any(ph.title in stored for ph in strategy.phases)  # the strategy output itself is NOT stored


async def test_queen_does_not_store_transient_output_or_secrets(service, db_session, project_id):
    run_id = make_run(db_session, project_id)
    llm = ScriptedLLM(extraction(
        ("context", "This run produced 2 phases and 3 tasks.", 1),
        ("fact", "Deploy with api_key=abcd1234efgh5678 in production", 5),
    ))
    await run_queen(queen_wf(llm, service), run_id, "Build an expense tracker", project_id)
    db_session.expire_all()
    assert [r.content for r in db_session.scalars(select(AgentMemory))] == ["This run produced 2 phases and 3 tasks."]


async def test_queen_with_nothing_worth_remembering_stores_nothing(service, db_session, project_id):
    run_id = make_run(db_session, project_id)
    await run_queen(queen_wf(ScriptedLLM(dict(REPLIES)), service), run_id, "Build an expense tracker", project_id)
    assert count(db_session) == 0


async def test_queen_repeat_runs_do_not_duplicate_memories(service, db_session, project_id):
    reply = extraction(("decision", "The expense tracker stores data in PostgreSQL.", 5))
    for i in range(3):
        run_id = make_run(db_session, project_id)
        await run_queen(queen_wf(ScriptedLLM(dict(reply)), service), run_id, "Build an expense tracker", project_id,
                        f"evt-{i}")
    assert count(db_session) == 1


async def test_queen_cross_run_persistence_run2_retrieves_what_run1_stored(session_factory, db_session, project_id):
    reply = extraction(("decision", "The expense tracker stores its data in PostgreSQL only.", 5))
    run1 = make_run(db_session, project_id)
    await run_queen(queen_wf(ScriptedLLM(dict(reply)), MemoryService(EmbeddingService(HashingBackend(), DIM))),
                    run1, "Build an expense tracker web app", project_id)

    llm2 = ScriptedLLM(dict(REPLIES))  # run 2: brand-new service, brand-new workflow
    run2 = make_run(db_session, project_id)
    await run_queen(queen_wf(llm2, MemoryService(EmbeddingService(HashingBackend(), DIM))),
                    run2, "Design the expense tracker data storage", project_id)
    assert "1. [decision] The expense tracker stores its data in PostgreSQL only." in strategy_prompt(llm2)


async def test_queen_fails_explicitly_when_embedding_fails_at_retrieval_or_storage(db_session, project_id, caplog):
    run_id = make_run(db_session, project_id)
    broken = MemoryService(EmbeddingService(FailingBackend(), DIM))
    with pytest.raises(Exception, match="cannot search memory"):
        await run_queen(queen_wf(ScriptedLLM(dict(REPLIES)), broken), run_id, "Build an expense tracker", project_id)

    class FailsOnlyOnStore(EmbeddingService):
        async def embed_text(self, text):  # retrieval works, storage fails
            if text.startswith("The expense"):
                raise EmbeddingError("provider down")
            return await super().embed_text(text)

    half = MemoryService(FailsOnlyOnStore(HashingBackend(), DIM))
    llm = ScriptedLLM(extraction(("decision", "The expense tracker stores data in PostgreSQL.", 5)))
    with pytest.raises(Exception, match="NOT stored"):
        await run_queen(queen_wf(llm, half), run_id, "Build an expense tracker", project_id)
    assert count(db_session) == 0


async def test_memory_logs_never_contain_memory_text_or_vectors(service, db_session, project_id, caplog):
    secret_text = "The expense tracker stores data in PostgreSQL."
    run_id = make_run(db_session, project_id)
    with caplog.at_level(logging.INFO):
        await run_queen(queen_wf(ScriptedLLM(extraction(("decision", secret_text, 5))), service), run_id,
                        "Build an expense tracker", project_id)
        await service.retrieve_memories(db_session, "expense tracker database", project_id, min_similarity=0.0)
    assert "Memory stored: type=decision" in caplog.text and "Memory retrieval completed" in caplog.text
    assert secret_text not in caplog.text and "[0." not in caplog.text
