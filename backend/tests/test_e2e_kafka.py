"""
End-to-end through a REAL Kafka broker: POST /runs -> API producer -> Kafka -> Scheduler consumer
(real confluent Consumer, manual commits) -> fake agents -> PostgreSQL. No LLM credits.

Skipped when no broker answers on KAFKA_BOOTSTRAP_SERVERS (`docker compose up -d kafka`).
"""

import threading
import time
import uuid

import pytest
from confluent_kafka.admin import AdminClient, NewTopic
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.main import app
from app.models import Event, Run, RunRevision, Task
from app.scheduler.consumer import SchedulerConsumer
from tests import fakes

pytestmark = pytest.mark.kafka

EXPECTED = [
    "run.created", "strategy.created", "architecture.created", "research.completed",
    "tasks.generated", "review.completed", "run.completed",
]


@pytest.fixture
def topic(monkeypatch):
    admin = AdminClient({"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS})
    try:
        admin.list_topics(timeout=5)
    except Exception as e:
        pytest.skip(f"Kafka not reachable: {e}")
    name = f"hivemind.e2e.{uuid.uuid4().hex[:8]}"
    for f in admin.create_topics([NewTopic(name, num_partitions=1)]).values():
        f.result(10)
    monkeypatch.setattr(settings, "KAFKA_TOPIC", name)  # read by the API lifespan
    return name


def start_scheduler(topic, group=None):
    sched = SchedulerConsumer(settings.KAFKA_BOOTSTRAP_SERVERS, topic, group or f"e2e-{uuid.uuid4().hex[:6]}")
    thread = threading.Thread(target=sched.start, daemon=True)
    thread.start()
    return sched, thread


def wait_terminal(session_factory, run_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with session_factory() as db:
            status = db.get(Run, run_id).status
        if status != "running":
            return status
        time.sleep(0.5)
    return "running"


def create_run(client):
    pid = client.post("/api/v1/projects/", json={"name": "e2e", "owner": "t", "goal_summary": "g"}).json()["id"]
    return client.post("/api/v1/runs/", json={"project_id": pid, "goal": "e2e goal"}).json()["id"]


def test_real_kafka_pipeline_completes(topic, monkeypatch, session_factory):
    fakes.install_fake_agents(monkeypatch)
    sched, thread = start_scheduler(topic)
    try:
        with TestClient(app) as client:  # runs the real lifespan (real KafkaEventBus)
            run_id = create_run(client)
            assert wait_terminal(session_factory, run_id) == "completed"

            with session_factory() as db:
                events = db.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.created_at)).all()
                assert [e.event_type for e in events] == EXPECTED
                assert db.scalars(select(Task).where(Task.run_id == run_id)).all().__len__() == 2
            assert fakes.CALLS == ["queen", "architect", "scout", "builder", "guardian"]
            status = client.get(f"/api/v1/workflow/{run_id}/status").json()
            assert status["status"] == "completed" and status["completed_stages"] == EXPECTED
    finally:
        sched.stop()
        thread.join(15)
    assert not thread.is_alive() and sched.event_bus.producer.flush(1) == 0


def test_real_kafka_failure_marks_run_failed(topic, monkeypatch, session_factory):
    fakes.install_fake_agents(monkeypatch)
    fakes.FAIL_STAGE.append("scout")
    sched, thread = start_scheduler(topic)
    try:
        with TestClient(app) as client:
            run_id = create_run(client)
            assert wait_terminal(session_factory, run_id) == "failed"
            failure = client.get(f"/api/v1/workflow/{run_id}/status").json()["failure"]
            assert failure["failed_stage"] == "scout"
    finally:
        sched.stop()
        thread.join(15)
    assert "builder" not in fakes.CALLS


def test_real_kafka_redelivery_after_scheduler_restart_does_not_rerun_agents(topic, monkeypatch, session_factory):
    """Fresh consumer group re-reads the whole topic from the start: every event is a duplicate."""
    fakes.install_fake_agents(monkeypatch)
    sched, thread = start_scheduler(topic)
    try:
        with TestClient(app) as client:
            run_id = create_run(client)
            assert wait_terminal(session_factory, run_id) == "completed"
    finally:
        sched.stop()
        thread.join(15)
    calls_before = list(fakes.CALLS)

    sched2, thread2 = start_scheduler(topic)  # new group id, earliest offset
    time.sleep(8)
    sched2.stop()
    thread2.join(15)
    assert fakes.CALLS == calls_before
    with session_factory() as db:
        assert len(db.scalars(select(Event).where(Event.run_id == run_id)).all()) == 7


# ── Guardian revision loop through real Kafka ───────────────────────────

REVISION_PATH = EXPECTED[:6] + ["revision.requested", "tasks.generated", "review.completed", "run.completed"]


def test_real_kafka_revision_loop_completes(topic, monkeypatch, session_factory):
    fakes.install_fake_agents(monkeypatch)
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    sched, thread = start_scheduler(topic)
    try:
        with TestClient(app) as client:
            run_id = create_run(client)
            assert wait_terminal(session_factory, run_id) == "completed"
            status = client.get(f"/api/v1/workflow/{run_id}/status").json()
            assert (status["revision_count"], status["revision_status"]) == (1, "approved")
        with session_factory() as db:
            events = db.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.created_at)).all()
            assert [e.event_type for e in events] == REVISION_PATH
            assert len({e.id for e in events}) == len(events)
            assert [t.revision_number for t in db.scalars(
                select(Task).where(Task.run_id == run_id).order_by(Task.revision_number, Task.title))] == [0, 0, 1, 1, 1]
    finally:
        sched.stop()
        thread.join(15)
    assert [g["revision"] for g in fakes.GUARDIAN_INPUTS] == [0, 1]


def test_real_kafka_scheduler_crash_during_revision_is_redelivered_and_builder_runs_once(
        topic, monkeypatch, session_factory):
    """Hard-crash the scheduler while it processes revision.requested (offset not committed), restart it with the
    same consumer group: Kafka redelivers, the revision completes exactly once, nothing is duplicated."""
    fakes.install_fake_agents(monkeypatch)
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    fakes.CRASH_ONCE.append("builder_revision")
    group = f"e2e-crash-{uuid.uuid4().hex[:6]}"

    sched1, thread1 = start_scheduler(topic, group)
    sched2 = thread2 = None
    try:
        with TestClient(app) as client:
            run_id = create_run(client)
            thread1.join(90)
            assert not thread1.is_alive(), "scheduler should have crashed while revising"

            with session_factory() as db:   # state at the moment of the crash
                assert db.get(Run, run_id).status == "running"
                (rev,) = db.scalars(select(RunRevision).where(RunRevision.run_id == run_id)).all()
                assert (rev.revision_number, rev.status) == (1, "requested")
                types = [e.event_type for e in db.scalars(
                    select(Event).where(Event.run_id == run_id).order_by(Event.created_at))]
                assert types == EXPECTED[:6]                      # revision.requested itself was not yet persisted
            assert fakes.CALLS.count("builder_revision") == 1 and fakes.BUILDER_REVISIONS == []

            sched2, thread2 = start_scheduler(topic, group)      # restart: same group -> redelivery
            assert wait_terminal(session_factory, run_id, timeout=90) == "completed"

            status = client.get(f"/api/v1/workflow/{run_id}/status").json()
            assert (status["status"], status["revision_count"], status["revision_status"]) == ("completed", 1, "approved")
        with session_factory() as db:
            events = db.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.created_at)).all()
            assert [e.event_type for e in events] == REVISION_PATH and len({e.id for e in events}) == len(events)
            revs = db.scalars(select(RunRevision).where(RunRevision.run_id == run_id)).all()
            assert [(r.revision_number, r.status) for r in revs] == [(1, "approved")]   # no duplicate revision record
            per_rev = {}
            for t in db.scalars(select(Task).where(Task.run_id == run_id)):
                per_rev[t.revision_number] = per_rev.get(t.revision_number, 0) + 1
            assert per_rev == {0: 2, 1: 3}                                             # no duplicate tasks
        assert len(fakes.BUILDER_REVISIONS) == 1                                       # revision completed exactly once
        assert fakes.CALLS.count("builder_revision") == 2                              # crashed attempt + the redelivery
        assert [g["revision"] for g in fakes.GUARDIAN_INPUTS] == [0, 1]                # Guardian saw the right revision
        assert fakes.GUARDIAN_INPUTS[1]["titles"][0] == "Task 1 (rev 1)"
    finally:
        for sc, th in ((sched1, thread1), (sched2, thread2)):
            if sc is not None:
                sc.stop()
                th.join(15)


def test_real_kafka_revision_limit_fails_the_run_with_max_revisions_exceeded(topic, monkeypatch, session_factory):
    """MAX_REVISIONS=1 and a Guardian that never approves: original review -> 1 revision -> re-review -> run.failed."""
    monkeypatch.setattr(settings, "MAX_REVISIONS", 1)
    fakes.install_fake_agents(monkeypatch)
    fakes.VERDICT[:] = ["needs_revision"]
    sched, thread = start_scheduler(topic)
    try:
        with TestClient(app) as client:
            run_id = create_run(client)
            assert wait_terminal(session_factory, run_id) == "failed"
            st = client.get(f"/api/v1/workflow/{run_id}/status").json()
            assert st["failure"]["error_type"] == "MAX_REVISIONS_EXCEEDED"
            assert (st["failure"]["revision_count"], st["failure"]["max_revisions"]) == (1, 1)
            assert st["failure"]["feedback"] and st["failure"]["requested_changes"]   # Guardian feedback preserved
        with session_factory() as db:
            types = [e.event_type for e in db.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.created_at))]
            assert types == EXPECTED[:6] + ["revision.requested", "tasks.generated", "review.completed", "run.failed"]
            assert [(r.revision_number, r.status) for r in db.scalars(
                select(RunRevision).where(RunRevision.run_id == run_id))] == [(1, "needs_revision")]
    finally:
        sched.stop()
        thread.join(15)
    assert fakes.CALLS.count("builder_revision") == 1 and fakes.CALLS.count("guardian") == 2  # no second revision


# ── WebSocket telemetry through real Kafka ──────────────────────────────

from tests.test_telemetry import Browser, event_types, is_state, open_ws  # noqa: E402  (helpers only)


def _persisted_ids(session_factory, run_id):
    with session_factory() as db:
        return {e.id for e in db.scalars(select(Event).where(Event.run_id == run_id))}


def test_real_kafka_events_reach_the_websocket_after_persistence(topic, monkeypatch, session_factory):
    """Kafka -> Scheduler -> PostgreSQL commit -> NOTIFY -> hub -> browser, across real processes' worth of plumbing."""
    fakes.install_fake_agents(monkeypatch)
    fakes.DELAY[0] = 0.3
    sched, thread = start_scheduler(topic)
    try:
        with TestClient(app) as client:
            assert app.state.telemetry_listener.connected.wait(10)
            run_id = create_run(client)
            with open_ws(client, run_id) as s:
                b = Browser(s)
                snap = b.recv(timeout=15)
                msgs = [snap] + b.until(is_state("completed"), timeout=60)
            got = snap["events"] + [m for m in msgs[1:] if m["type"] == "workflow.event"]
            assert [e["event_type"] for e in got] == EXPECTED
            assert {e["event_id"] for e in got} == _persisted_ids(session_factory, run_id)   # everything sent was persisted
            assert msgs[-1]["state"]["status"] == "completed"
            assert all(a["status"] == "completed" for a in msgs[-1]["state"]["agents"].values())
            assert client.get(f"/api/v1/workflow/{run_id}/status").json()["agents"] == msgs[-1]["state"]["agents"]
    finally:
        sched.stop()
        thread.join(15)


def test_real_kafka_disconnect_and_reconnect_recovers_missed_events(topic, monkeypatch, session_factory):
    fakes.install_fake_agents(monkeypatch)
    fakes.DELAY[0] = 0.4
    sched, thread = start_scheduler(topic)
    try:
        with TestClient(app) as client:
            assert app.state.telemetry_listener.connected.wait(10)
            run_id = create_run(client)
            seen = {}
            with open_ws(client, run_id) as s:
                b = Browser(s)
                snap = b.recv(timeout=15)
                for e in snap["events"]:
                    seen[e["event_id"]] = e
                while len(seen) < 2:                      # take a couple of live events, then vanish
                    m = b.recv(timeout=30)
                    if m["type"] == "workflow.event":
                        seen[m["event_id"]] = m
                last_seen = list(seen)[-1]
            assert wait_terminal(session_factory, run_id, timeout=90) == "completed"   # run continued without us

            with open_ws(client, run_id, last_event_id=last_seen) as s2:
                snap2 = Browser(s2).recv(timeout=15)
            assert snap2["mode"] == "resume"
            recovered = [e["event_id"] for e in snap2["events"]]
            assert len(set(recovered) & set(seen)) == 0                   # nothing delivered twice
            everything = list(seen) + recovered
            assert set(everything) == _persisted_ids(session_factory, run_id) and len(everything) == len(EXPECTED)
            assert [seen[i]["event_type"] for i in seen] + [e["event_type"] for e in snap2["events"]] == EXPECTED
            assert snap2["state"]["status"] == "completed"
    finally:
        sched.stop()
        thread.join(15)


def test_real_kafka_revision_run_is_visible_over_the_websocket(topic, monkeypatch, session_factory):
    fakes.install_fake_agents(monkeypatch)
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    fakes.DELAY[0] = 0.1
    sched, thread = start_scheduler(topic)
    try:
        with TestClient(app) as client:
            assert app.state.telemetry_listener.connected.wait(10)
            run_id = create_run(client)
            with open_ws(client, run_id) as s:
                b = Browser(s)
                snap = b.recv(timeout=15)
                msgs = b.until(is_state("completed"), timeout=60)
            types = [e["event_type"] for e in snap["events"]] + event_types(msgs)
            assert types == REVISION_PATH
            states = [snap["state"]] + [m["state"] for m in msgs if m["type"] == "workflow.state"]
            assert any(st["agents"]["guardian"]["status"] == "revision" for st in states) or \
                   any(e["event_type"] == "revision.requested" for e in snap["events"] + msgs)
            assert states[-1]["revision"]["count"] == 1 and states[-1]["revision"]["status"] == "approved"
    finally:
        sched.stop()
        thread.join(15)
