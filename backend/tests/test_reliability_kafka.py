"""
Phase 5 — Kafka/scheduler crash-point reliability. The REAL SchedulerConsumer.start() loop runs against MiniKafka
with crashes injected at every point of the per-event flow; after each scenario the DB invariants must hold.
"""

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import Event, Project, Run, RunRevision, Task
from app.schemas.run import RunCreate
from app.services.run_service import create_run
from tests import scenario_agents as sa
from tests.invariants import check_invariants
from tests.minikafka import Harness

STAGES = ["strategy.created", "architecture.created", "research.completed", "tasks.generated", "review.completed",
          "run.created"]
POINTS = ["before_publish", "after_publish", "at_commit", "after_db_commit"]


@pytest.fixture(autouse=True)
def agents(monkeypatch):
    sa.install(monkeypatch)


def submit(h: Harness, sf, goal: str, project: str = "p1") -> str:
    with sf() as db:
        if db.get(Project, project) is None:
            db.add(Project(id=project, name=project, owner="o", goal_summary="g"))
            db.commit()
        return create_run(db, RunCreate(project_id=project, goal=goal), h.api_bus()).id


def state(sf, rid):
    with sf() as db:
        run = db.get(Run, rid)
        types = list(db.scalars(select(Event.event_type).where(Event.run_id == rid).order_by(Event.created_at)))
        return run.status, types


def assert_healthy(sf):
    with sf() as db:
        assert check_invariants(db, max_revisions=settings.MAX_REVISIONS) == []


def assert_once_each(rid, **exceptions):
    """Every agent ran exactly once (the Guardian twice when one revision happened, etc.)."""
    want = {"queen": 1, "architect": 1, "scout": 1, "builder": 1, "guardian": 1, "builder_revision": 1, **exceptions}
    got = {s: n for (r, s), n in sa.EXEC.items() if r == rid}
    assert all(got.get(k, 0) == v for k, v in want.items() if k != "builder_revision" or got.get(k)), got
    assert got.get("builder_revision", 0) in (0, 1), got


# handler for run.created runs Queen; the crash targets the event being PROCESSED (its type), which is the
# stage whose handler/publish/commit is interrupted.
EXEC_STAGE = {"run.created": "queen", "strategy.created": "architect", "architecture.created": "scout",
              "research.completed": "builder", "tasks.generated": "guardian"}


@pytest.mark.parametrize("point", POINTS)
@pytest.mark.parametrize("etype", list(EXEC_STAGE))
def test_crash_matrix_approved_path(session_factory, point, etype):
    h = Harness(session_factory)
    h.hooks.arm(point, etype)
    rid = submit(h, session_factory, "tag=a v=approved")
    crashes = h.run_until_done()
    assert h.hooks.fired == [(point, etype)] and crashes == 1
    status, types = state(session_factory, rid)
    assert status == "completed", types
    assert types.count("run.completed") == 1
    stage = EXEC_STAGE[etype]
    # crashed before the DB commit => the stage is re-executed on restart; after commit => executed exactly once
    expected = 1 if point == "after_db_commit" else 2
    assert sa.EXEC[(rid, stage)] == expected, (point, etype, dict(sa.EXEC))
    # ... and no other stage ever runs twice
    assert all(n == 1 for (r, s), n in sa.EXEC.items() if r == rid and s != stage)
    assert_healthy(session_factory)


@pytest.mark.parametrize("point", POINTS)
@pytest.mark.parametrize("etype", ["review.completed", "revision.requested", "tasks.generated"])
def test_crash_matrix_revision_path(session_factory, point, etype):
    h = Harness(session_factory)
    h.hooks.arm(point, etype, nth=2 if etype != "revision.requested" else 1)
    rid = submit(h, session_factory, "tag=r v=needs,approved")
    h.run_until_done()
    status, types = state(session_factory, rid)
    assert status == "completed", types
    assert types.count("revision.requested") == 1
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(RunRevision).where(RunRevision.run_id == rid)) == 1
        revs = set(db.scalars(select(Task.revision_number).where(Task.run_id == rid)))
    assert revs == {0, 1}
    assert_healthy(session_factory)


@pytest.mark.parametrize("point", POINTS)
def test_crash_during_max_revisions_failure(session_factory, point):
    h = Harness(session_factory)
    n = settings.MAX_REVISIONS + 1
    h.hooks.arm(point, "review.completed", nth=n)
    rid = submit(h, session_factory, "tag=m v=needs")
    h.run_until_done()
    status, types = state(session_factory, rid)
    assert status == "failed" and types.count("run.failed") == 1
    assert types.count("revision.requested") == settings.MAX_REVISIONS
    assert_healthy(session_factory)


def test_multiple_crashes_in_one_run(session_factory):
    h = Harness(session_factory)
    for etype in EXEC_STAGE:
        h.hooks.arm("at_commit", etype)
        h.hooks.arm("after_publish", etype)
    rid = submit(h, session_factory, "tag=mc v=needs,approved")
    assert h.run_until_done() >= 8
    assert state(session_factory, rid)[0] == "completed"
    assert_healthy(session_factory)


@pytest.mark.parametrize("etype", ["strategy.created", "tasks.generated", "review.completed"])
def test_publish_failure_is_retried_not_lost(session_factory, etype):
    """Kafka rejects the child publish: nothing is persisted, the event is retried, the run completes."""
    h = Harness(session_factory)
    h.hooks.publish_fail_types = {etype}
    rid = submit(h, session_factory, "tag=pf v=approved")
    sched, thread = h.start()
    import time
    time.sleep(0.6)
    assert state(session_factory, rid)[0] == "running"  # stuck behind the failing publish, not failed / not skipped
    h.hooks.publish_fail_types = set()
    from tests.minikafka import wait_idle
    assert wait_idle(h.kafka, thread) == "idle"
    sched.stop(); thread.join(10)
    assert state(session_factory, rid)[0] == "completed"
    assert_healthy(session_factory)


def test_consumer_poll_errors_do_not_kill_the_loop(session_factory):
    h = Harness(session_factory)
    h.hooks.poll_errors = 3
    rid = submit(h, session_factory, "tag=pe v=approved")
    assert h.run_until_done() == 0
    assert state(session_factory, rid)[0] == "completed"


def test_offset_commit_failure_redelivers_and_is_idempotent(session_factory):
    h = Harness(session_factory)
    h.hooks.commit_errors = 2
    rid = submit(h, session_factory, "tag=oc v=approved")
    h.run_until_done()
    assert state(session_factory, rid)[0] == "completed"
    assert all(n == 1 for (r, _), n in sa.EXEC.items() if r == rid), dict(sa.EXEC)
    assert_healthy(session_factory)


def test_duplicate_delivery_of_every_event(session_factory):
    """Every event is delivered twice by the broker: each agent still runs exactly once, the run completes once."""
    from tests.minikafka import MiniKafka

    class Dup(MiniKafka):
        def append(self, raw):
            super().append(raw)
            return super().append(raw)

    h = Harness(session_factory, kafka=Dup())
    rid = submit(h, session_factory, "tag=d v=needs,approved")
    assert h.run_until_done() == 0
    status, types = state(session_factory, rid)
    assert status == "completed", types
    assert_once_each(rid, guardian=2)
    assert types.count("run.completed") == 1
    assert_healthy(session_factory)


def test_duplicate_delivery_after_completion_changes_nothing(session_factory):
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=dc v=needs,approved")
    h.run_until_done()
    before = state(session_factory, rid)
    for i in range(h.kafka.size()):
        h.kafka.duplicate(i)
    h.run_until_done()
    assert state(session_factory, rid) == before
    assert_once_each(rid, guardian=2)
    assert_healthy(session_factory)


def test_concurrent_workers_on_the_same_event_run_the_agent_at_most_twice_and_persist_once(session_factory):
    """Two scheduler processes racing on one message (a consumer-group rebalance): the DB PK makes one winner."""
    import threading
    from app.events.schemas import KafkaEvent
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=cw v=approved delay=0.2")
    first = h.kafka.events()[0]
    a, b = h.new_scheduler(), h.new_scheduler()
    ts = [threading.Thread(target=x.process, args=(KafkaEvent.model_validate_json(first.to_json_bytes()),)) for x in (a, b)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Event).where(Event.run_id == rid, Event.event_type == "run.created")) == 1
    h.run_until_done()
    assert state(session_factory, rid)[0] == "completed"
    assert_healthy(session_factory)
