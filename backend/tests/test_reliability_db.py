"""
Phase 5 — database reliability: transient outages are retried, permanent persistence errors are isolated, every
result is one atomic transaction, and the invariant checker really detects corruption.
"""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError

from agents.builder.schemas import TaskGraph, TaskNode
from app.core.config import settings
from app.core.metrics import metrics
from app.models import Event, Run, RunRevision, Task
from app.services import event_service
from tests import scenario_agents as sa
from tests.invariants import check_invariants, lifecycle_violation
from tests.minikafka import Harness
from tests.test_reliability_kafka import assert_healthy, state, submit


@pytest.fixture(autouse=True)
def agents(monkeypatch):
    sa.install(monkeypatch)
    metrics.reset()


def test_transient_db_error_is_retried_and_the_run_completes(session_factory, monkeypatch):
    real = event_service.add_kafka_event
    boom = {"n": 2}

    def flaky(db, event):
        if boom["n"] > 0 and event.event_type == "research.completed":
            boom["n"] -= 1
            raise OperationalError("INSERT", {}, Exception("connection reset by peer (simulated)"))
        return real(db, event)

    monkeypatch.setattr(event_service, "add_kafka_event", flaky)
    monkeypatch.setattr("app.scheduler.consumer.RETRY_PAUSE_S", 0.05)
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=t v=needs,approved")
    h.run_until_done()
    assert state(session_factory, rid)[0] == "completed"  # a DB blip never fails the run
    assert metrics.get("infra_retries") >= 2
    assert_healthy(session_factory)


def test_permanent_db_error_rolls_back_all_tasks_and_fails_only_that_run(session_factory, monkeypatch):
    """10 tasks, the 7th cannot be stored: no partial tasks, the run fails, another run is unaffected."""
    class BadBuilder(sa.SBuilder):
        async def generate_task_graph(self, run_id, goal, plan, report):
            if "tag=bad" not in goal:
                return await super().generate_task_graph(run_id, goal, plan, report)
            sa._enter(run_id, goal, "builder")
            nodes = [TaskNode.model_construct(
                id=i, title=f"bad Task {i}", description="d", priority="high", dependencies=[],
                estimated_complexity="low", required_files=[], acceptance_criteria=["ok"],
                assigned_agent="x" * 80 if i == 7 else "developer_agent") for i in range(1, 11)]
            return TaskGraph.model_construct(workflow_run_id=run_id, goal=goal, summary="s", tasks=nodes)

    monkeypatch.setattr("app.scheduler.consumer.BuilderService", BadBuilder)
    h = Harness(session_factory)
    bad = submit(h, session_factory, "tag=bad v=approved")
    good = submit(h, session_factory, "tag=good v=approved")
    h.run_until_done()
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Task).where(Task.run_id == bad)) == 0  # atomic
    status, types = state(session_factory, bad)
    assert status == "failed" and types.count("run.failed") == 1
    assert state(session_factory, good)[0] == "completed"  # the consumer was not blocked
    assert metrics.get("poison_events") == 1
    assert_healthy(session_factory)


def test_unrecordable_poison_event_is_skipped_not_looped(session_factory, monkeypatch):
    """Even the failure record cannot be written for one run: its event is skipped (CRITICAL), the queue keeps moving."""
    real = event_service.add_kafka_event
    h = Harness(session_factory)
    stuck = submit(h, session_factory, "tag=p v=approved")
    other = submit(h, session_factory, "tag=q v=approved")

    def selective(db, event):
        if event.run_id == stuck and event.event_type in ("research.completed", "run.failed"):
            raise ValueError("cannot store this event (simulated)")
        return real(db, event)

    monkeypatch.setattr(event_service, "add_kafka_event", selective)
    h.run_until_done()
    assert metrics.get("poison_events_unrecorded") >= 1
    assert state(session_factory, other)[0] == "completed"  # the queue kept moving


def test_result_and_event_row_are_one_transaction(session_factory):
    """A crash right before COMMIT leaves neither the consumed-event row nor any effect (tasks / revision)."""
    h = Harness(session_factory)
    h.hooks.arm("at_commit", "research.completed")  # Builder result: tasks are written in this txn
    rid = submit(h, session_factory, "tag=tx v=approved")
    sched, thread = h.start()
    thread.join(20)
    with session_factory() as db:
        types = set(db.scalars(select(Event.event_type).where(Event.run_id == rid)))
        assert "research.completed" not in types
        assert db.scalar(select(func.count()).select_from(Task).where(Task.run_id == rid)) == 0
    h.run_until_done()
    assert state(session_factory, rid)[0] == "completed"
    assert_healthy(session_factory)


def test_revision_row_and_event_are_atomic(session_factory):
    h = Harness(session_factory)
    h.hooks.arm("at_commit", "review.completed", nth=1)
    rid = submit(h, session_factory, "tag=ra v=needs,approved")
    sched, thread = h.start()
    thread.join(20)
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(RunRevision).where(RunRevision.run_id == rid)) == 0
    h.run_until_done()
    assert state(session_factory, rid)[0] == "completed"
    assert_healthy(session_factory)


# ── the checker itself must detect corruption (a checker that never fails proves nothing) ──────────────────────


def _completed_run(session_factory, goal="tag=c v=needs,approved"):
    h = Harness(session_factory)
    rid = submit(h, session_factory, goal)
    h.run_until_done()
    return rid


def _violations(session_factory):
    with session_factory() as db:
        return check_invariants(db, max_revisions=settings.MAX_REVISIONS)


def _exec(session_factory, sql, **p):
    with session_factory() as db:
        db.execute(text(sql), p)
        db.commit()


def test_checker_passes_on_a_healthy_database(session_factory):
    _completed_run(session_factory)
    assert _violations(session_factory) == []


@pytest.mark.parametrize("corrupt,marker", [
    ("UPDATE runs SET status='running' WHERE id=:r", "STUCK"),
    ("UPDATE runs SET status='failed' WHERE id=:r", "I4"),
    ("DELETE FROM tasks WHERE run_id=:r AND revision_number=1", "I8"),
    ("DELETE FROM events WHERE run_id=:r AND event_type='revision.requested'", "I3"),
    ("UPDATE run_revisions SET status='requested' WHERE run_id=:r", "I7"),
    ("UPDATE tasks SET title='other Task 1' WHERE run_id=:r AND revision_number=0", "I10"),
    ("UPDATE runs SET duration_ms=NULL WHERE id=:r", "duration_ms"),
])
def test_checker_detects_corruption(session_factory, corrupt, marker):
    rid = _completed_run(session_factory)
    _exec(session_factory, corrupt, r=rid)
    found = _violations(session_factory)
    assert found and any(marker in v for v in found), found


def test_checker_detects_duplicate_terminal_and_stray_events(session_factory):
    rid = _completed_run(session_factory, "tag=e v=approved")
    _exec(session_factory,
          "INSERT INTO events (id, run_id, event_type, agent, payload, cost_usd, latency_ms, created_at) "
          "VALUES ('dup-1', :r, 'run.completed', 'x', '{}', 0, 0, now() + interval '1 second')", r=rid)
    assert any("I3" in v or "I4" in v for v in _violations(session_factory))


def test_lifecycle_rules():
    ok = ["run.created", "strategy.created", "architecture.created", "research.completed", "tasks.generated",
          "review.completed", "revision.requested", "tasks.generated", "review.completed", "run.completed"]
    assert lifecycle_violation(ok) is None and lifecycle_violation(ok[:3]) is None
    assert lifecycle_violation(ok[:4] + ["review.completed"]) is not None
    assert lifecycle_violation(ok + ["strategy.created"]) is not None
    assert lifecycle_violation(ok[:3] + ["run.failed"]) is None
    assert lifecycle_violation(["run.completed", "run.completed"]) is not None
