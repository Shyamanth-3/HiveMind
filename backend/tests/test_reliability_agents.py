"""
Phase 5 — agent failure injection, Guardian verdict handling and the revision bound, through the real scheduler loop.
No LLM is called: scenario agents raise / time out / return odd verdicts on demand.
"""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import Event
from tests import scenario_agents as sa
from tests.minikafka import Harness
from tests.test_reliability_kafka import assert_healthy, state, submit

STAGE_FAILS = ["queen", "architect", "scout", "builder", "guardian"]


@pytest.fixture(autouse=True)
def agents(monkeypatch):
    sa.install(monkeypatch)


def failed_payload(sf, rid):
    with sf() as db:
        return db.scalars(select(Event).where(Event.run_id == rid, Event.event_type == "run.failed")).one().payload


@pytest.mark.parametrize("mode", ["fail", "timeout"])
@pytest.mark.parametrize("stage", STAGE_FAILS)
def test_agent_failure_or_timeout_fails_the_run_once_with_the_right_stage(session_factory, stage, mode):
    h = Harness(session_factory)
    rid = submit(h, session_factory, f"tag=f v=approved {mode}={stage}")
    assert h.run_until_done() == 0
    status, types = state(session_factory, rid)
    assert status == "failed" and types.count("run.failed") == 1 and types[-1] == "run.failed"
    p = failed_payload(session_factory, rid)
    assert p["failed_stage"] == stage
    assert p["error_type"] == ("TimeoutError" if mode == "timeout" else "RuntimeError")
    assert sa.EXEC[(rid, stage)] == 1  # a failed agent is never silently re-run by the scheduler
    assert_healthy(session_factory)


def test_builder_revision_failure_fails_the_run(session_factory):
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=br v=needs,approved fail=builder_revision")
    h.run_until_done()
    assert state(session_factory, rid)[0] == "failed"
    assert failed_payload(session_factory, rid)["failed_stage"] == "builder"
    assert_healthy(session_factory)


def test_a_failed_run_does_not_touch_other_runs(session_factory):
    h = Harness(session_factory)
    bad = submit(h, session_factory, "tag=x v=approved fail=scout")
    good = submit(h, session_factory, "tag=y v=needs,approved")
    h.run_until_done()
    assert state(session_factory, bad)[0] == "failed" and state(session_factory, good)[0] == "completed"
    assert_healthy(session_factory)


def test_no_events_are_processed_after_a_failure(session_factory):
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=z v=approved fail=architect")
    h.run_until_done()
    _, types = state(session_factory, rid)
    assert types == ["run.created", "strategy.created", "run.failed"]


@pytest.mark.parametrize("verdicts,status,revisions", [
    ("approved", "completed", 0),
    ("needs,approved", "completed", 1),
    ("needs,needs,approved", "completed", 2),
    ("rejected", "failed", 0),
    ("needs,rejected", "failed", 1),
])
def test_guardian_verdict_paths(session_factory, verdicts, status, revisions):
    h = Harness(session_factory)
    rid = submit(h, session_factory, f"tag=g v={verdicts}")
    h.run_until_done()
    got, types = state(session_factory, rid)
    assert got == status and types.count("revision.requested") == revisions
    assert_healthy(session_factory)


def test_unknown_guardian_verdict_fails_instead_of_looping(session_factory):
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=u v=maybe")
    h.run_until_done()
    assert state(session_factory, rid)[0] == "failed"
    # rejected while the scheduler rehydrates the review (the loop controller), before any routing decision
    assert failed_payload(session_factory, rid)["error_type"] == "ValidationError"
    assert sa.EXEC[(rid, "guardian")] == 1  # no revision loop was started
    assert_healthy(session_factory)


def test_always_needs_revision_stops_at_max_revisions(session_factory):
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=inf v=needs")
    h.run_until_done()
    status, types = state(session_factory, rid)
    assert status == "failed" and types.count("revision.requested") == settings.MAX_REVISIONS
    assert failed_payload(session_factory, rid)["error_type"] == "MAX_REVISIONS_EXCEEDED"
    assert sa.EXEC[(rid, "guardian")] == settings.MAX_REVISIONS + 1  # bounded: original + MAX revisions
    assert_healthy(session_factory)


@pytest.mark.parametrize("point", ["before_publish", "at_commit", "after_db_commit"])
def test_max_revisions_is_not_exceeded_across_crashes_and_restarts(session_factory, point):
    h = Harness(session_factory)
    for nth in range(1, settings.MAX_REVISIONS + 2):
        h.hooks.arm(point, "review.completed", nth)
        h.hooks.arm(point, "revision.requested", nth)
    rid = submit(h, session_factory, "tag=cr v=needs")
    h.run_until_done()
    status, types = state(session_factory, rid)
    assert status == "failed" and types.count("revision.requested") == settings.MAX_REVISIONS
    assert_healthy(session_factory)


def test_max_revisions_is_read_from_settings(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REVISIONS", 1)
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=mr v=needs")
    h.run_until_done()
    status, types = state(session_factory, rid)
    assert status == "failed" and types.count("revision.requested") == 1
    with session_factory() as db:
        from tests.invariants import check_invariants
        assert check_invariants(db, max_revisions=1) == []


@pytest.mark.parametrize("exc_name", ["LLMTimeoutError", "LLMRateLimitError", "LLMAuthenticationError",
                                      "LLMProviderError", "LLMInvalidResponseError"])
def test_neutral_llm_errors_keep_the_phase5_failure_semantics(session_factory, monkeypatch, exc_name):
    """Any provider's failure reaches the scheduler as a neutral LLMError: run failed once, agent not re-run,
    error_type names the neutral class (never a provider SDK exception)."""
    from agents.llm import errors

    class Boom(sa.SScout):
        async def generate_research(self, run_id, goal, plan):
            sa._enter(run_id, goal, "scout")
            raise getattr(errors, exc_name)("provider said no")

    monkeypatch.setattr("app.scheduler.consumer.ScoutService", Boom)
    h = Harness(session_factory)
    rid = submit(h, session_factory, "tag=le v=approved")
    assert h.run_until_done() == 0
    assert state(session_factory, rid)[0] == "failed"
    p = failed_payload(session_factory, rid)
    assert (p["failed_stage"], p["error_type"]) == ("scout", exc_name)
    assert sa.EXEC[(rid, "scout")] == 1
    assert_healthy(session_factory)
