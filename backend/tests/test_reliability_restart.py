"""
Phase 5 — restart matrix and concurrency on a REAL Kafka broker (skipped when none is reachable): the scheduler
process dies (hard SystemExit, offset uncommitted) at each stage, a new one joins the same consumer group, and the
run must finish exactly once with clean invariants. Plus 10 concurrent runs through one real consumer.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests import fakes
from tests.invariants import check_invariants
from tests.test_e2e_kafka import create_run, start_scheduler, topic, wait_terminal  # noqa: F401

pytestmark = pytest.mark.kafka


@pytest.mark.parametrize("stage", ["queen", "architect", "scout", "builder", "guardian", "builder_revision"])
def test_scheduler_crash_at_each_stage_then_restart_completes_the_run_once(stage, topic, monkeypatch, session_factory):
    fakes.install_fake_agents(monkeypatch)
    fakes.VERDICT[:] = ["needs_revision", "approved"]   # exercises the revision path too
    fakes.CRASH_ONCE.append(stage)
    group = f"rs-{uuid.uuid4().hex[:6]}"
    s1, t1 = start_scheduler(topic, group)
    s2 = t2 = None
    try:
        with TestClient(app) as client:
            run_id = create_run(client)
            t1.join(90)
            assert not t1.is_alive(), f"scheduler should have died in {stage}"
            s2, t2 = start_scheduler(topic, group)
            assert wait_terminal(session_factory, run_id, timeout=90) == "completed"
        with session_factory() as db:
            assert check_invariants(db, max_revisions=settings.MAX_REVISIONS) == []
        assert fakes.CALLS.count(stage) == 2 or stage == "guardian"  # crashed attempt + the redelivery
    finally:
        for sc, th in ((s1, t1), (s2, t2)):
            if sc is not None:
                sc.stop()
                th.join(15)


def test_ten_concurrent_runs_on_real_kafka(topic, monkeypatch, session_factory):
    fakes.install_fake_agents(monkeypatch)
    fakes.VERDICT[:] = ["approved"]
    s, t = start_scheduler(topic)
    try:
        with TestClient(app) as client:
            pid = client.post("/api/v1/projects/", json={"name": "c", "owner": "t", "goal_summary": "g"}).json()["id"]
            ids = [client.post("/api/v1/runs/", json={"project_id": pid, "goal": f"goal {i}"}).json()["id"] for i in range(10)]
            assert [wait_terminal(session_factory, r, timeout=120) for r in ids] == ["completed"] * 10
        with session_factory() as db:
            assert check_invariants(db, max_revisions=settings.MAX_REVISIONS) == []
    finally:
        s.stop()
        t.join(15)
