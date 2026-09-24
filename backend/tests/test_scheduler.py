"""
Phase 1 scheduler tests: event persistence, run lifecycle, failure path, idempotency,
offset-commit semantics. Real PostgreSQL, fake Kafka bus, fake agents.
"""

import pytest
from sqlalchemy import func, select

from app.events.kafka_event_bus import EventPublishError, KafkaEventBus
from app.events.schemas import KafkaEvent
from app.models import Event, Run, Task
from app.scheduler import consumer as consumer_mod
from app.scheduler.consumer import SchedulerConsumer
from tests import fakes

HAPPY_PATH = [
    "run.created", "strategy.created", "architecture.created", "research.completed",
    "tasks.generated", "review.completed", "run.completed",
]


@pytest.fixture
def scheduler(monkeypatch, bus, session_factory):
    fakes.install_fake_agents(monkeypatch)
    return SchedulerConsumer("unused", "t", "g", consumer=object(), event_bus=bus,
                             session_factory=session_factory)


@pytest.fixture
def run_id(client):
    pid = client.post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"}).json()["id"]
    res = client.post("/api/v1/runs/", json={"project_id": pid, "goal": "Build a thing"})
    assert res.status_code == 201
    return res.json()["id"]


def pump(scheduler, bus, start=0):
    """Feed published events back into the scheduler like Kafka would (JSON round-trip), until quiet."""
    i = start
    while i < len(bus.published):
        raw = bus.published[i].to_json_bytes()
        scheduler.process(KafkaEvent.model_validate_json(raw))
        i += 1
    return i


def events_of(db, run_id):
    return db.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.created_at, Event.id)).all()


def run_status(db, run_id):
    db.expire_all()
    return db.get(Run, run_id).status


# ── happy path ──────────────────────────────────────────────────────────


def test_full_pipeline_completes_and_persists_everything(scheduler, bus, run_id, db_session, client):
    pump(scheduler, bus)

    assert fakes.CALLS == ["queen", "architect", "scout", "builder", "guardian"]
    assert [e.event_type for e in events_of(db_session, run_id)] == HAPPY_PATH
    assert len({e.id for e in events_of(db_session, run_id)}) == 7  # event_id is the PK

    run = db_session.get(Run, run_id)
    assert run.status == "completed"
    assert run.duration_ms is not None and run.duration_ms >= 0

    tasks = db_session.scalars(select(Task).where(Task.run_id == run_id).order_by(Task.title)).all()
    assert [t.title for t in tasks] == ["Task 1", "Task 2"]
    assert tasks[1].depends_on == [tasks[0].id]
    assert tasks[0].details["priority"] == "high"

    status = client.get(f"/api/v1/workflow/{run_id}/status").json()
    assert status["status"] == "completed" and status["is_completed"] is True
    assert status["current_stage"] is None and status["failure"] is None
    assert status["completed_stages"] == HAPPY_PATH

    outputs = client.get(f"/api/v1/workflow/{run_id}/outputs").json()["outputs"]
    assert set(outputs) == {"strategy", "architecture_plan", "research_report", "task_graph", "validation_report"}


def test_running_run_reports_current_stage(scheduler, bus, run_id, client):
    scheduler.process(KafkaEvent.model_validate_json(bus.published[0].to_json_bytes()))
    status = client.get(f"/api/v1/workflow/{run_id}/status").json()
    assert status["status"] == "running" and status["current_stage"] == "strategy.created"


# ── verdicts ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("verdict,error_type", [
    ("rejected", "ReviewRejected"),  # needs_revision is the Guardian revision loop: see tests/test_revision.py
])
def test_non_approved_verdict_fails_run_not_completes(scheduler, bus, run_id, db_session, verdict, error_type):
    fakes.VERDICT[0] = verdict
    pump(scheduler, bus)

    types = [e.event_type for e in events_of(db_session, run_id)]
    assert types[-2:] == ["review.completed", "run.failed"]
    assert "run.completed" not in types
    failed = events_of(db_session, run_id)[-1].payload
    assert failed["error_type"] == error_type and failed["verdict"] == verdict
    assert run_status(db_session, run_id) == "failed"


# ── failure path ────────────────────────────────────────────────────────


@pytest.mark.parametrize("stage", ["queen", "architect", "scout", "builder", "guardian"])
def test_agent_failure_produces_run_failed(scheduler, bus, run_id, db_session, stage):
    fakes.FAIL_STAGE.append(stage)
    pump(scheduler, bus)

    assert run_status(db_session, run_id) == "failed"
    failed = [e for e in events_of(db_session, run_id) if e.event_type == "run.failed"]
    assert len(failed) == 1
    assert failed[0].payload["failed_stage"] == stage
    assert failed[0].payload["error_type"] == "RuntimeError"
    assert f"{stage} exploded" in failed[0].payload["message"]
    assert fakes.CALLS[-1] == stage  # nothing ran after the failure


def test_failure_message_never_leaks_api_key(scheduler, bus, run_id, db_session, monkeypatch):
    class Leaky(fakes.FakeQueen):
        async def generate_strategy(self, run_id, goal, *args, **kwargs):
            raise RuntimeError("401 for key test-key-not-real")

    monkeypatch.setattr(consumer_mod, "QueenService", Leaky)
    pump(scheduler, bus)
    payload = [e for e in events_of(db_session, run_id) if e.event_type == "run.failed"][0].payload
    assert "test-key-not-real" not in payload["message"] and "[REDACTED]" in payload["message"]


def test_publish_failure_of_next_event_is_retried_and_does_not_fail_the_run(scheduler, bus, run_id, db_session):
    """A broker error is infrastructure: it propagates (the consume loop retries the message), the run is NOT failed."""
    bus.fail_types = {"strategy.created"}
    with pytest.raises(RuntimeError, match="kafka unavailable"):
        pump(scheduler, bus)
    assert run_status(db_session, run_id) == "running"
    assert [e.event_type for e in events_of(db_session, run_id)] == []  # nothing half-committed
    bus.fail_types = set()
    pump(scheduler, bus, start=len(bus.published) - 1)  # redelivery of run.created
    assert [e.event_type for e in events_of(db_session, run_id)][-1] == "run.completed"


def test_kafka_down_for_run_failed_still_marks_run_failed_in_db(scheduler, bus, run_id, db_session):
    fakes.FAIL_STAGE.append("scout")
    bus.fail_types = {"run.failed"}
    pump(scheduler, bus)
    assert run_status(db_session, run_id) == "failed"
    assert [e.event_type for e in events_of(db_session, run_id)][-1] == "run.failed"


def test_events_after_terminal_state_are_ignored(scheduler, bus, run_id, db_session):
    pump(scheduler, bus)
    calls = list(fakes.CALLS)
    late = KafkaEvent(event_type="strategy.created", source="x", run_id=run_id,
                      payload={"goal": "g", "strategy": {}})
    scheduler.process(late)
    assert fakes.CALLS == calls and run_status(db_session, run_id) == "completed"


def test_event_for_unknown_run_is_dropped_without_error(scheduler):
    scheduler.process(KafkaEvent(event_type="run.created", source="x", run_id="nope", payload={"goal": "g"}))
    assert fakes.CALLS == []


# ── idempotency ─────────────────────────────────────────────────────────


def test_duplicate_event_id_is_processed_once(scheduler, bus, run_id, db_session):
    created = bus.published[0]
    scheduler.process(created)
    scheduler.process(created)  # redelivery

    assert fakes.CALLS == ["queen"]
    assert len([e for e in bus.published if e.event_type == "strategy.created"]) == 1
    assert db_session.scalar(select(func.count()).select_from(Event).where(Event.id == str(created.event_id))) == 1


def test_redelivery_after_crash_republishes_same_child_event_id(scheduler, bus, run_id, db_session):
    """Crash after publish but before the DB commit: the retry emits a child with the SAME event_id,
    so the consumer dedups it instead of running the next agent twice."""
    created = bus.published[0]
    scheduler.process(created)
    first_child = bus.published[-1]

    db_session.execute(Event.__table__.delete().where(Event.id == str(created.event_id)))
    db_session.commit()  # simulate: the event row never got committed
    scheduler.process(created)

    assert bus.published[-1].event_id == first_child.event_id
    scheduler.process(first_child)
    scheduler.process(bus.published[-1])  # duplicate child delivery
    assert fakes.CALLS.count("architect") == 1


def test_restart_mid_run_resumes_without_rerunning_finished_stages(monkeypatch, bus, session_factory, run_id, db_session):
    fakes.install_fake_agents(monkeypatch)
    first = SchedulerConsumer("u", "t", "g", consumer=object(), event_bus=bus, session_factory=session_factory)
    first.process(bus.published[0])
    first.process(bus.published[1])  # queen + architect done
    del first  # "restart": brand-new scheduler, same DB, Kafka redelivers everything from the start

    second = SchedulerConsumer("u", "t", "g", consumer=object(), event_bus=bus, session_factory=session_factory)
    pump(second, bus)
    assert fakes.CALLS == ["queen", "architect", "scout", "builder", "guardian"]
    assert run_status(db_session, run_id) == "completed"


# ── Kafka offset semantics ──────────────────────────────────────────────


class Msg:
    def __init__(self, event: KafkaEvent, offset: int):
        self._v, self._o = event.to_json_bytes(), offset

    def value(self): return self._v
    def error(self): return None
    def offset(self): return self._o
    def topic(self): return "t"
    def partition(self): return 0


class FakeConsumer:
    def __init__(self, scheduler_ref, msgs):
        self.msgs, self.commits, self.seeks, self.closed = list(msgs), [], [], False
        self.scheduler_ref = scheduler_ref

    def subscribe(self, topics): pass

    def poll(self, timeout):
        if self.msgs:
            return self.msgs.pop(0)
        self.scheduler_ref[0].stop()
        return None

    def commit(self, message, asynchronous): self.commits.append(message.offset())
    def seek(self, tp): self.seeks.append(tp.offset)
    def close(self): self.closed = True


def make_looping(monkeypatch, bus, session_factory, events):
    monkeypatch.setattr(consumer_mod, "RETRY_PAUSE_S", 0)
    ref = []
    fc = FakeConsumer(ref, [Msg(e, i) for i, e in enumerate(events)])
    s = SchedulerConsumer("u", "t", "g", consumer=fc, event_bus=bus, session_factory=session_factory)
    ref.append(s)
    return s, fc


def test_offset_committed_after_success_and_producer_closed_on_shutdown(monkeypatch, bus, session_factory, run_id):
    fakes.install_fake_agents(monkeypatch)
    s, fc = make_looping(monkeypatch, bus, session_factory, [bus.published[0]])
    s.start()
    assert fc.commits == [0] and fc.seeks == []
    assert fc.closed and bus.closed  # consumer closed AND producer flushed/closed


def test_offset_committed_when_failure_is_recorded_as_run_failed(monkeypatch, bus, session_factory, run_id, db_session):
    fakes.install_fake_agents(monkeypatch)
    fakes.FAIL_STAGE.append("queen")
    s, fc = make_looping(monkeypatch, bus, session_factory, [bus.published[0]])
    s.start()
    assert fc.commits == [0]  # failure is recorded (run.failed), not retried forever
    assert [e.event_type for e in bus.published][-1] == "run.failed"


def test_offset_not_committed_on_infrastructure_error_and_message_is_retried(monkeypatch, bus, session_factory, run_id):
    fakes.install_fake_agents(monkeypatch)
    calls = {"n": 0}

    def flaky_factory():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("db down")
        return session_factory()

    s, fc = make_looping(monkeypatch, bus, flaky_factory, [bus.published[0]])
    s.session_factory = flaky_factory
    fc.msgs.append(Msg(bus.published[0], 0))  # same offset redelivered after the seek
    s.start()
    assert fc.seeks == [0]        # rewound to the failed message
    assert fc.commits == [0]      # committed only once the retry succeeded
    assert fakes.CALLS == ["queen"]


def test_poison_message_is_committed_and_skipped(monkeypatch, bus, session_factory):
    class Bad:
        def value(self): return b"not json"
        def error(self): return None
        def offset(self): return 7
        def topic(self): return "t"
        def partition(self): return 0

    monkeypatch.setattr(consumer_mod, "RETRY_PAUSE_S", 0)
    ref = []
    fc = FakeConsumer(ref, [Bad()])
    s = SchedulerConsumer("u", "t", "g", consumer=fc, event_bus=bus, session_factory=session_factory)
    ref.append(s)
    s.start()
    assert fc.commits == [7]


# ── producer + API + health ─────────────────────────────────────────────


def test_kafka_bus_publish_raises_when_delivery_fails():
    bus = KafkaEventBus("127.0.0.1:1", "t")  # nothing listens there
    bus.DELIVERY_TIMEOUT_S = 2
    with pytest.raises(EventPublishError):
        bus.publish(KafkaEvent(event_type="run.created", source="x", run_id="r"))


def test_run_creation_marks_run_failed_if_event_cannot_be_published(client, bus, db_session):
    """Kafka unavailable at POST /runs: deterministic 503 carrying the run id; the run is 'failed', never stuck 'running'."""
    pid = client.post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"}).json()["id"]
    bus.fail_types = {"run.created"}
    res = client.post("/api/v1/runs/", json={"project_id": pid, "goal": "g"})
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert "event bus is unavailable" in detail["message"]
    (run,) = db_session.scalars(select(Run)).all()
    assert run.id == detail["run_id"] and run.status == "failed"


def test_system_services_reports_postgres_online(client):
    services = {s["name"]: s for s in client.get("/api/v1/system/services").json()}
    assert services["PostgreSQL"]["status"] == "online"
