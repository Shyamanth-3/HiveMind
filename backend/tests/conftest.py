"""
Test setup: a real PostgreSQL + pgvector database (`hivemind_test`), built with
`alembic upgrade head` so the migrations are exercised too. No real API keys are used.

Requires the compose Postgres (`docker compose up -d postgres`).
"""

import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]

_base = (
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or dotenv_values(BACKEND / ".env").get("DATABASE_URL")
)
_test_url = make_url(_base)
if not _test_url.database.endswith("_test"):
    _test_url = _test_url.set(database="hivemind_test")

# Must happen before any `app` import: settings are read once at import time.
os.environ.update(
    DATABASE_URL=_test_url.render_as_string(hide_password=False),
    GROQ_API_KEY="test-key-not-real",
    REDIS_URL="redis://unused",
    EMBEDDING_PROVIDER="none",  # unit tests inject their own embedding service; no model download
)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.dependencies import get_event_bus  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from tests.fakes import FakeBus  # noqa: E402

TABLES = "agent_logs, agent_memories, memory_chunks, events, tasks, runs, projects"


@pytest.fixture(scope="session")
def engine():
    admin = create_engine(_test_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": _test_url.database}
        ).scalar()
        if not exists:
            # template0: template1 may carry a stale collation version
            conn.execute(text(f'CREATE DATABASE "{_test_url.database}" TEMPLATE template0'))
    admin.dispose()

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")

    eng = create_engine(_test_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    """Clean tables before each test; the scheduler commits for real, so no rollback trick."""
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture
def db_session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture
def bus():
    return FakeBus()


@pytest.fixture
def client(session_factory, bus):
    def override_get_db():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_event_bus] = lambda: bus
    yield TestClient(app)  # no `with`: skip the lifespan (it would open a real Kafka producer)
    app.dependency_overrides.clear()
