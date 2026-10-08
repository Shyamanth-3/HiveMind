"""
HiveMind — FastAPI Application Entry Point.

This is the top-level file that:
1. Creates the FastAPI app with metadata for the OpenAPI docs.
2. Adds CORS middleware so the Next.js frontend can call the API.
3. Registers all API routers under a versioned prefix.

The app follows a layered architecture:
    Client → Router → Service → ORM → PostgreSQL
"""

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.middleware import (
    BodySizeLimitMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware, request_id_var,
)
from app.core.redaction import install_log_redaction
from app.events.kafka_event_bus import KafkaEventBus
from agents.llm.factory import log_llm_config
from app.telemetry.hub import TelemetryHub
from app.telemetry.listener import NotifyListener

from dotenv import load_dotenv

load_dotenv()
# Basic logging setup for FastAPI
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
install_log_redaction()  # provider errors can echo credentials; scrub every log record
logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup and shutdown.

    Startup: Initialize Kafka producer and store in app state.
    Shutdown: Flush remaining Kafka messages.
    """
    settings.assert_production_ready()  # ENVIRONMENT=production: refuse to start on an unsafe configuration
    logger.info(f"🐝 {settings.APP_NAME} backend starting... (environment={settings.ENVIRONMENT})")
    logger.info(f"   Database: {settings.DATABASE_URL.split('@')[-1]}")
    log_llm_config()
    
    # Initialize KafkaEventBus and attach to app state
    event_bus = KafkaEventBus(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_TOPIC,
    )
    app.state.event_bus = event_bus

    # WebSocket telemetry: observational only. The listener wakes the hub when the Scheduler commits events.
    hub = TelemetryHub()
    listener = NotifyListener(hub, asyncio.get_running_loop())
    listener.start()
    app.state.telemetry_hub = hub
    app.state.telemetry_listener = listener
    
    yield
    
    logger.info(f"🐝 {settings.APP_NAME} backend shutting down...")
    await hub.close_all()      # close WebSockets first (clients get 1001 and reconnect elsewhere)
    listener.stop()
    event_bus.close()          # flush the Kafka producer
    from app.db.database import engine
    engine.dispose()           # release pooled PostgreSQL connections


# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="Event-Driven Multi-Agent AI Operating System — Backend API",
    version="0.1.0",
    lifespan=lifespan,
    # The interactive docs / schema describe every endpoint: development and test only.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# ── CORS ────────────────────────────────────────────────────────────────────
# The Next.js frontend (port 3000) needs to call this API (port 8000).
# Without CORS middleware, browsers block cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)
# Outermost last: request context wraps everything so every response (including 413/500) carries X-Request-ID.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(RequestContextMiddleware)


# ── Error responses: never internals ────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 with only WHERE and WHY. FastAPI's default echoes the submitted input (which can be a password)."""
    errors = [{"loc": [str(p) for p in e.get("loc", ())], "msg": str(e.get("msg", "invalid"))} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """500 without stack trace, paths or connection strings; the detail stays in the (redacted) server log."""
    rid = request.scope.get("request_id") or request_id_var.get()
    logger.error("Unhandled error | request=%s %s %s: %s", rid, request.method, request.url.path,
                 type(exc).__name__, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": rid},
                        headers={"X-Request-ID": rid})

# ── Routers ─────────────────────────────────────────────────────────────────
# Health check — kept outside /api/v1 so load balancers can hit it directly.
from app.api.health import router as health_router
from app.api.router import api_router
from app.api.ws import router as ws_router

app.include_router(health_router)
app.include_router(ws_router)  # /ws/runs/{run_id}: outside /api/v1, like /health
app.include_router(api_router, prefix=settings.API_V1_PREFIX)