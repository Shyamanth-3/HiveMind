"""
Database engine, session factory, and dependency injection.

Why this file exists:
- Creates a single SQLAlchemy engine (connection pool) shared across the app.
- Provides `SessionLocal` factory for creating database sessions.
- Provides `Base` — the declarative base all ORM models inherit from.
- Provides `get_db()` — a FastAPI dependency that yields a session per request
  and guarantees cleanup (close) when the request finishes.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# ── Engine ──────────────────────────────────────────────────────────────────
# The engine manages the connection pool to PostgreSQL.
# pool_pre_ping=True ensures stale connections are recycled automatically.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

# ── Session Factory ─────────────────────────────────────────────────────────
# sessionmaker produces Session instances bound to our engine.
# autocommit=False → we control transaction boundaries explicitly.
# autoflush=False  → we flush only when we explicitly commit.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ── Declarative Base ────────────────────────────────────────────────────────
# Every ORM model inherits from Base. SQLAlchemy uses Base.metadata to
# discover tables and generate DDL.
class Base(DeclarativeBase):
    pass


# ── FastAPI Dependency ──────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session for a single request, then close it.

    Usage in routers:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...

    The `finally` block guarantees the session is returned to the pool
    even if the request handler raises an exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()