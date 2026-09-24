from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.metrics import metrics
from app.db.database import get_db
from app.models import Run, RunRevision

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
        "websocket_runs": {r: hub.client_count(r) for r in hub.run_ids()} if hub else {},
    }


@router.get("/metrics")
def operational_metrics(request: Request, db: Session = Depends(get_db)):
    """
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
        "api_process": {**metrics.snapshot(), "websocket_clients_now": hub.client_count() if hub else 0},
    }
