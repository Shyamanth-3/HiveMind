"""
HiveMind — FastAPI Application Entry Point.

This is the top-level file that:
1. Creates the FastAPI app with metadata for the OpenAPI docs.
2. Adds CORS middleware so the Next.js frontend can call the API.
3. Registers all API routers under a versioned prefix.

The app follows a layered architecture:
    Client → Router → Service → ORM → PostgreSQL
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


# ── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup and shutdown.

    Startup: Log that the server is ready.
    Shutdown: (future) close Redis connections, drain queues, etc.
    """
    print(f"🐝 {settings.APP_NAME} backend starting...")
    print(f"   Database: {settings.DATABASE_URL.split('@')[-1]}")
    yield
    print(f"🐝 {settings.APP_NAME} backend shutting down...")


# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="Event-Driven Multi-Agent AI Operating System — Backend API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────────────────
# The Next.js frontend (port 3000) needs to call this API (port 8000).
# Without CORS middleware, browsers block cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────────────────────
# Health check — kept outside /api/v1 so load balancers can hit it directly.
from app.api.health import router as health_router
from app.api.router import api_router

app.include_router(health_router)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)