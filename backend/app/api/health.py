import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.core.config import settings
from app.core.metrics import metrics
from app.db.database import SessionLocal, get_db
from app.models import Run, RunRevision, User

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/health",
    tags=["Health"]
)


@router.get("/")
def health(request: Request):
    hub = getattr(request.app.state, "telemetry_hub", None)
    return {
        "Status": "Healthy",
        # WebSocket telemetry observability: currently connected browser sockets (and per run)
        "websocket_clients": hub.client_count() if hub else 0,
        # (per-run connection counts are admin-only: see /health/metrics; run ids must not be public)
    }


@router.get("/live")
def live() -> dict:
    """Liveness: the process is up and the event loop answers. Checks NO dependency, so a database or Kafka blip
    never gets a healthy container restarted."""
    return {"status": "alive"}


@router.get("/ready")
def ready(request: Request, response: Response) -> dict:
    """
    Readiness: can this instance serve traffic right now? PostgreSQL and the Kafka producer must answer. Only
    booleans are returned (no hosts, no errors); details stay in the server log. HTTP 503 = take out of rotation.
    """
    checks = {"database": _check_database(), "kafka": _check_kafka(request)}
    ok = all(v == "ok" for v in checks.values())
    if not ok:
        response.status_code = 503
    return {"status": "ready" if ok else "not_ready", "checks": checks}


def _check_database() -> str:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("Readiness: database check failed (%s)", type(exc).__name__)
        return "unavailable"


def _check_kafka(request: Request) -> str:
    bus = getattr(request.app.state, "event_bus", None)
    producer = getattr(bus, "producer", None)
    if producer is None:
        return "unavailable"
    try:
        producer.list_topics(topic=settings.KAFKA_TOPIC, timeout=2.0)
        return "ok"
    except Exception as exc:
        logger.warning("Readiness: kafka check failed (%s)", type(exc).__name__)
        return "unavailable"


@router.get("/metrics")
def operational_metrics(request: Request, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    """INTERNAL (administrators only). 
    Operational metrics. `database` totals are derived from PostgreSQL, so they cover the Scheduler process too;
    `api_process` counters (websocket connections, memory/embedding latency, ...) are this API process only. The
    Scheduler logs its own `metrics {...}` snapshot every 60 s and on shutdown.
    """
    by_status = dict(db.execute(select(Run.status, func.count()).group_by(Run.status)).all())
    failures = db.execute(text(
        "SELECT payload->>'failed_stage' AS stage, payload->>'error_type' AS error_type, count(*) "
        "FROM events WHERE event_type = 'run.failed' GROUP BY 1, 2 ORDER BY 3 DESC")).all()
    hub = getattr(request.app.state, "telemetry_hub", None)
    return {
        "database": {
            "runs_total": sum(by_status.values()),
            "runs_by_status": by_status,
            "run_failures": [{"stage": s, "error_type": e, "count": c} for s, e, c in failures],
            "revisions_total": db.scalar(select(func.count()).select_from(RunRevision)) or 0,
            "revision_limit_failures": sum(c for _, e, c in failures if e == "MAX_REVISIONS_EXCEEDED"),
            "avg_run_duration_ms": db.scalar(select(func.avg(Run.duration_ms)).where(Run.status == "completed")),
        },
        "api_process": {**metrics.snapshot(), "websocket_clients_now": hub.client_count() if hub else 0,
                        "websocket_runs": {r: hub.client_count(r) for r in hub.run_ids()} if hub else {}},
    }
