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
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.events.kafka_event_bus import KafkaEventBus

# Basic logging setup for FastAPI
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup and shutdown.

    Startup: Initialize Kafka producer and store in app state.
    Shutdown: Flush remaining Kafka messages.
    """
    logger.info(f"🐝 {settings.APP_NAME} backend starting...")
    logger.info(f"   Database: {settings.DATABASE_URL.split('@')[-1]}")
    
    # Initialize KafkaEventBus and attach to app state
    event_bus = KafkaEventBus(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_TOPIC,
    )
    app.state.event_bus = event_bus
    
    yield
    
    logger.info(f"🐝 {settings.APP_NAME} backend shutting down...")
    event_bus.close()


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