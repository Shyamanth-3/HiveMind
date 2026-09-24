"""
Phase 5 — WebSocket telemetry reliability. The socket is observational: whatever happens to it (lost NOTIFY, killed
LISTEN connection, disconnects) the database stays the source of truth and REST/WS/DB must agree.
"""

import pytest
from sqlalchemy import text

from app.main import app
from tests.test_telemetry import (  # noqa: F401  (fixtures + helpers shared with the Phase 4 suite)
    Browser, api, event_types, feed, is_state, open_ws, run_id, scheduler, second_run_id, wait_until,
)
from tests import fakes


def test_lost_notify_is_recovered_by_the_safety_poll(api, scheduler, bus, run_id, monkeypatch):
    listener = app.state.telemetry_listener
    real_wake = listener._wake
    monkeypatch.setattr(listener, "_wake", lambda rid: real_wake(None) if rid is None else None)  # NOTIFYs are "lost"
    monkeypatch.setattr(listener, "poll_s", 2.0)  # shorten the 5 s safety poll
    with open_ws(api, run_id) as ws:
        b = Browser(ws)
        assert b.recv()["type"] == "workflow.snapshot"
        feed(scheduler, bus)
        got = b.until(is_state("completed"), timeout=20)
        assert "run.completed" in event_types(got)


def test_killed_listen_connection_reconnects_and_streams_again(api, scheduler, bus, run_id, session_factory):
    listener = app.state.telemetry_listener
    with session_factory() as db:  # terminate the LISTEN backend like a network drop / DB restart would
        db.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE query ILIKE 'LISTEN%' AND pid <> pg_backend_pid()"))
        db.commit()
    wait_until(lambda: not listener.connected.is_set(), 5)  # may already have reconnected
    assert listener.connected.wait(30), "listener did not reconnect"
    with open_ws(api, run_id) as ws:
        b = Browser(ws)
        assert b.recv()["type"] == "workflow.snapshot"
        feed(scheduler, bus)
        assert "run.completed" in event_types(b.until(is_state("completed"), timeout=20))


def _rest(api, run_id):
    return api.get(f"/api/v1/workflow/{run_id}/status").json()


@pytest.mark.parametrize("stage", ["running", "completed", "failed", "revision_pending"])
def test_rest_ws_and_db_agree_at_each_state(api, scheduler, bus, run_id, session_factory, stage):
    if stage == "failed":
        fakes.FAIL_STAGE.append("scout")
    if stage == "revision_pending":
        fakes.VERDICT[:] = ["needs_revision", "approved"]
    if stage == "running":
        feed(scheduler, bus, limit=2)
    elif stage == "revision_pending":
        feed(scheduler, bus, limit=6)  # through review.completed(needs_revision); revision.requested not consumed yet
    else:
        feed(scheduler, bus)
    with open_ws(api, run_id) as ws:
        snap = Browser(ws).recv()
    rest = _rest(api, run_id)
    st = snap["state"]
    with session_factory() as db:
        db_status = db.execute(text("SELECT status FROM runs WHERE id = :r"), {"r": run_id}).scalar()
    assert snap["type"] == "workflow.snapshot"
    assert st["status"] == rest["status"] == db_status
    assert st["agents"] == rest["agents"] and st["current_stage"] == rest["current_stage"]
    assert st["last_event_id"] == rest["last_event_id"]
    expected = {"running": "running", "revision_pending": "running", "completed": "completed", "failed": "failed"}[stage]
    assert st["status"] == expected
    if stage == "revision_pending":
        assert st["revision"]["count"] == rest["revision_count"]
