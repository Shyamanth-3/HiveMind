"""Phase 5 — observability: redaction, correlation ids, metrics, stale-run reporting, input validation."""

import logging
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.core.metrics import Metrics, metrics
from app.core.redaction import SecretRedactingFilter, redact_secrets
from app.services.run_service import find_stale_runs
from tests import scenario_agents as sa
from tests.minikafka import Harness
from tests.test_reliability_kafka import state, submit

KEYS = ["gsk_" + "a1B2c3D4e5F6g7H8i9J0k1L2", "sk-" + "abcdefghijklmnopqrstuvwx", "Bearer " + "abcdefghijklmnop1234567890"]


@pytest.mark.parametrize("secret", KEYS)
def test_secrets_are_redacted_but_uuids_survive(secret):
    out = redact_secrets(f"provider said: invalid key {secret} run=3f2a9c1e-7b1d-4e0a-9d55-0a1b2c3d4e5f")
    assert secret not in out and "3f2a9c1e-7b1d-4e0a-9d55-0a1b2c3d4e5f" in out


def test_log_filter_scrubs_message_args_and_tracebacks():
    rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "auth failed with %s", (KEYS[0],), None)
    try:
        raise RuntimeError(f"boom {KEYS[1]}")
    except RuntimeError:
        import sys
        rec.exc_info = sys.exc_info()
    assert SecretRedactingFilter().filter(rec)
    text_out = rec.getMessage() + (rec.exc_text or "")
    assert KEYS[0] not in text_out and KEYS[1] not in text_out


def test_metrics_registry():
    m = Metrics()
    m.inc("a"); m.inc("a", 2); m.inc("b", stage="x")
    with m.timer("t"):
        pass
    snap = m.snapshot()
    assert m.get("a") == 3 and m.get("b", stage="x") == 1 and snap["timings"]
    m.reset()
    assert m.get("a") == 0


def test_scheduler_metrics_and_correlated_logs(session_factory, monkeypatch, caplog):
    sa.install(monkeypatch)
    metrics.reset()
    caplog.set_level(logging.INFO)
    h = Harness(session_factory)
    ok = submit(h, session_factory, "tag=o1 v=needs,approved")
    bad = submit(h, session_factory, "tag=o2 v=approved fail=scout")
    h.run_until_done()
    assert metrics.get("runs_completed") == 1 and metrics.get("runs_failed") == 1
    assert metrics.get("revisions_requested") == 1 and metrics.get("agent_failures", stage="scout") == 1
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert f"run={ok}" in logs and f"run={bad}" in logs and "event=" in logs  # every line names run + event


def test_stale_runs_are_reported_never_auto_failed(session_factory, client):
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=st v=approved")  # created, scheduler never started
    with session_factory() as db:
        db.execute(text("UPDATE runs SET created_at = now() - interval '2 hours' WHERE id = :r"), {"r": rid})
        db.commit()
        assert [r["run_id"] for r in find_stale_runs(db, timedelta(minutes=30))] == [rid]
        assert find_stale_runs(db, timedelta(hours=3)) == []
    body = client.get("/api/v1/workflow/stale?older_than_minutes=30").json()
    assert [r["run_id"] for r in body["runs"]] == [rid]
    assert state(session_factory, rid)[0] == "running"  # reporting changed nothing
    st = client.get(f"/api/v1/workflow/{rid}/status").json()
    assert st["stale"] is True and st["idle_seconds"] >= 3600


def test_health_metrics_endpoint(session_factory, client, monkeypatch):
    sa.install(monkeypatch)
    h = Harness(session_factory)
    submit(h, session_factory, "tag=hm v=needs,approved")
    submit(h, session_factory, "tag=hf v=approved fail=builder")
    h.run_until_done()
    body = client.get("/health/metrics").json()["database"]
    assert body["runs_by_status"] == {"completed": 1, "failed": 1} and body["revisions_total"] == 1
    assert body["run_failures"] == [{"stage": "builder", "error_type": "RuntimeError", "count": 1}]
    assert client.get("/health/").json()["Status"] == "Healthy"  # existing contract unchanged


def test_run_status_is_validated(client):
    pid = client.post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"}).json()["id"]
    rid = client.post("/api/v1/runs/", json={"project_id": pid, "goal": "g"}).json()["id"]
    assert client.patch(f"/api/v1/runs/{rid}", json={"status": "bogus"}).status_code == 422
    assert client.patch(f"/api/v1/runs/{rid}", json={"status": "completed"}).status_code == 200
