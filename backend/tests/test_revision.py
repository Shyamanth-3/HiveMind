"""
Phase 3 Guardian revision loop tests: fake agents + fake bus, real PostgreSQL. (Real-Kafka restart tests
live in test_e2e_kafka.py.) No LLM calls.

Loop under test:
  review.completed --needs_revision--> revision.requested --Builder--> tasks.generated --Guardian--> review.completed
  approved -> run.completed | rejected -> run.failed | revision_count >= MAX_REVISIONS -> run.failed
"""

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text

from agents.guardian.revision import RevisionRequest, build_revision_request, guardian_feedback, revision_id_for
from agents.guardian.schemas import (
    ArchitectureReview, DependencyReview, MaintainabilityReview, PerformanceReview,
    SecurityReview, ValidationReport,
)
from app.core.config import settings
from app.events.schemas import KafkaEvent
from app.models import Event, Run, RunRevision, Task
from app.scheduler.consumer import SchedulerConsumer
from tests import fakes

FIRST = ["run.created", "strategy.created", "architecture.created", "research.completed",
         "tasks.generated", "review.completed"]
REVISE = ["revision.requested", "tasks.generated", "review.completed"]


@pytest.fixture
def scheduler(monkeypatch, bus, session_factory):
    fakes.install_fake_agents(monkeypatch)
    return SchedulerConsumer("unused", "t", "g", consumer=object(), event_bus=bus, session_factory=session_factory)


@pytest.fixture
def run_id(client):
    pid = client.post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"}).json()["id"]
    return client.post("/api/v1/runs/", json={"project_id": pid, "goal": "Build a thing"}).json()["id"]


def pump(scheduler, bus, start=0):
    i = start
    while i < len(bus.published):
        scheduler.process(KafkaEvent.model_validate_json(bus.published[i].to_json_bytes()))
        i += 1
    return i


def run_until_published(scheduler, bus, event_type):
    """Process events until `event_type` has been PUBLISHED (but not yet processed). Returns its event."""
    i = 0
    while i < len(bus.published) and not any(e.event_type == event_type for e in bus.published):
        scheduler.process(KafkaEvent.model_validate_json(bus.published[i].to_json_bytes()))
        i += 1
    return next(e for e in bus.published if e.event_type == event_type)


def events_of(db, run_id):
    return db.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.created_at, Event.id)).all()


def types_of(db, run_id):
    return [e.event_type for e in events_of(db, run_id)]


def revisions_of(db, run_id):
    db.expire_all()
    return db.scalars(select(RunRevision).where(RunRevision.run_id == run_id).order_by(RunRevision.revision_number)).all()


def tasks_by_revision(db, run_id):
    db.expire_all()
    rows = db.execute(select(Task.revision_number, func.count()).where(Task.run_id == run_id)
                      .group_by(Task.revision_number).order_by(Task.revision_number)).all()
    return {r: c for r, c in rows}


def status(db, run_id):
    db.expire_all()
    return db.get(Run, run_id).status


# ── unit: payload, identity, numbering ──────────────────────────────────


def report(verdict="needs_revision", **over):
    base = dict(
        workflow_run_id="00000000-0000-0000-0000-000000000001", goal="g", summary="Plan lacks deployment detail",
        overall_verdict=verdict,
        architecture_review=ArchitectureReview(is_sound=False, feedback="No deployment topology"),
        dependency_review=DependencyReview(has_cycles=False, feedback="fine"),
        security_review=SecurityReview(is_secure=False, feedback="No auth design"),
        performance_review=PerformanceReview(is_performant=True, feedback="fine"),
        maintainability_review=MaintainabilityReview(is_maintainable=True, feedback="fine"),
        recommendations=["Add a deployment task", "Design authentication"],
    )
    return ValidationReport(**{**base, **over})


def valid_request(**over):
    args = dict(run_id="r1", source_review_event_id="e1", revision_number=1, max_revisions=3, feedback=["a"],
                requested_changes=["b"], reason="why")
    args.update(over)
    args.setdefault("revision_id", revision_id_for(args["run_id"], args["source_review_event_id"], args["revision_number"]))
    return RevisionRequest(**args)


def test_revision_ids_are_deterministic_and_distinguish_run_review_and_number():
    a = revision_id_for("run", "review-1", 1)
    assert a == revision_id_for("run", "review-1", 1)
    assert len({a, revision_id_for("run", "review-1", 2), revision_id_for("run", "review-2", 1),
                revision_id_for("run2", "review-1", 1)}) == 4
    assert len(a) == 36


def test_build_revision_request_from_guardian_report():
    req = build_revision_request(report(), "run-1", "review-evt", 1, 3)
    assert req.revision_number == 1 and req.max_revisions == 3 and req.source_review_event_id == "review-evt"
    assert req.revision_id == revision_id_for("run-1", "review-evt", 1)
    assert req.feedback == ["architecture: No deployment topology", "security: No auth design"]  # only flagged areas
    assert req.requested_changes == ["Add a deployment task", "Design authentication"]
    assert req.reason == "Plan lacks deployment detail"


def test_feedback_falls_back_to_every_area_and_changes_to_the_summary():
    ok = dict(architecture_review=ArchitectureReview(is_sound=True, feedback="a"),
              security_review=SecurityReview(is_secure=True, feedback="s"), recommendations=[])
    r = report(**ok)
    assert len(guardian_feedback(r)) == 5  # nothing flagged -> all five areas
    assert build_revision_request(r, "run", "e", 1, 3).requested_changes == ["Plan lacks deployment detail"]


@pytest.mark.parametrize("over", [
    dict(revision_number=0), dict(revision_number=4), dict(max_revisions=0), dict(feedback=[]),
    dict(requested_changes=[]), dict(reason=""), dict(revision_id="not-the-derived-id"),
])
def test_revision_request_is_strictly_validated(over):
    with pytest.raises(ValidationError):
        valid_request(**over)


def test_revision_numbering_follows_the_previous_revision(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision", "needs_revision", "approved"]
    pump(scheduler, bus)
    assert [r.revision_number for r in revisions_of(db_session, run_id)] == [1, 2]
    reqs = [RevisionRequest.model_validate(e.payload["revision"]) for e in bus.published
            if e.event_type == "revision.requested"]
    assert [q.revision_number for q in reqs] == [1, 2] and all(q.max_revisions == settings.MAX_REVISIONS for q in reqs)


# ── scenarios ───────────────────────────────────────────────────────────


def test_1_approved_on_first_review_runs_guardian_once_and_no_revision(scheduler, bus, run_id, db_session, client):
    pump(scheduler, bus)
    assert types_of(db_session, run_id) == FIRST + ["run.completed"]
    assert fakes.CALLS.count("guardian") == 1 and "builder_revision" not in fakes.CALLS
    assert revisions_of(db_session, run_id) == [] and status(db_session, run_id) == "completed"
    st = client.get(f"/api/v1/workflow/{run_id}/status").json()
    assert (st["revision_count"], st["current_revision"], st["revision_status"], st["max_revisions"]) == \
           (0, 0, "none", settings.MAX_REVISIONS)


def test_2_one_revision_then_approved(scheduler, bus, run_id, db_session, client):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    pump(scheduler, bus)

    assert types_of(db_session, run_id) == FIRST + REVISE + ["run.completed"]
    assert fakes.CALLS.count("builder") == 1 and fakes.CALLS.count("builder_revision") == 1
    assert fakes.CALLS.count("guardian") == 2 and status(db_session, run_id) == "completed"

    evs = events_of(db_session, run_id)
    first_review, second_tasks, second_review = evs[5], evs[7], evs[8]
    (rev,) = revisions_of(db_session, run_id)
    assert (rev.revision_number, rev.status) == (1, "approved")
    assert rev.source_review_event_id == first_review.id            # which review caused it
    assert rev.tasks_event_id == second_tasks.id                    # which Builder output followed
    assert rev.review_event_id == second_review.id                  # which review judged that output
    assert rev.feedback == ["architecture: add deployment detail"]
    assert rev.requested_changes == ["Add a deployment task", "Add test tasks"]
    assert rev.id == revision_id_for(run_id, first_review.id, 1) and rev.completed_at is not None

    # Builder got the Guardian feedback AND the previous output; Guardian reviewed the NEW output
    assert fakes.BUILDER_REVISIONS == [{
        "revision": 1, "feedback": ["architecture: add deployment detail"],
        "requested_changes": ["Add a deployment task", "Add test tasks"],
        "previous_titles": ["Task 1", "Task 2"]}]
    assert [g["revision"] for g in fakes.GUARDIAN_INPUTS] == [0, 1]
    assert fakes.GUARDIAN_INPUTS[0]["titles"] == ["Task 1", "Task 2"]
    assert fakes.GUARDIAN_INPUTS[1]["titles"] == ["Task 1 (rev 1)", "Task 2 (rev 1)", "Task 3 (rev 1)"]
    assert fakes.GUARDIAN_INPUTS[1]["previous"] == ["Add a deployment task", "Add test tasks"]

    assert tasks_by_revision(db_session, run_id) == {0: 2, 1: 3}    # history kept, current = highest
    st = client.get(f"/api/v1/workflow/{run_id}/status").json()
    assert (st["status"], st["revision_count"], st["current_revision"], st["revision_status"]) == \
           ("completed", 1, 1, "approved")
    assert st["revisions"][0]["revision_id"] == rev.id
    out = client.get(f"/api/v1/workflow/{run_id}/outputs").json()
    assert out["current_revision"] == 1 and out["outputs"]["task_graph"]["summary"] == "tasks rev 1"
    assert out["outputs"]["validation_report"]["overall_verdict"] == "approved"


def test_3_multiple_revisions_are_each_persisted(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision", "needs_revision", "approved"]
    pump(scheduler, bus)
    assert types_of(db_session, run_id) == FIRST + REVISE + REVISE + ["run.completed"]
    r1, r2 = revisions_of(db_session, run_id)
    assert [(r.revision_number, r.status) for r in (r1, r2)] == [(1, "needs_revision"), (2, "approved")]
    assert r1.review_event_id and r2.review_event_id and r1.tasks_event_id != r2.tasks_event_id
    assert r2.source_review_event_id == r1.review_event_id          # revision 2 was requested by review of revision 1
    assert tasks_by_revision(db_session, run_id) == {0: 2, 1: 3, 2: 3}
    assert [g["revision"] for g in fakes.GUARDIAN_INPUTS] == [0, 1, 2]
    assert [b["previous_titles"][0] for b in fakes.BUILDER_REVISIONS] == ["Task 1", "Task 1 (rev 1)"]
    assert status(db_session, run_id) == "completed"


def test_4_revision_limit_fails_the_run_and_no_extra_builder_runs(scheduler, bus, run_id, db_session, monkeypatch, client):
    monkeypatch.setattr(settings, "MAX_REVISIONS", 2)
    fakes.VERDICT[:] = ["needs_revision"]  # Guardian never approves
    pump(scheduler, bus)

    assert fakes.CALLS.count("builder_revision") == 2 and fakes.CALLS.count("guardian") == 3  # no 4th Builder run
    assert types_of(db_session, run_id) == FIRST + REVISE + REVISE + ["run.failed"]
    assert status(db_session, run_id) == "failed"
    failed = events_of(db_session, run_id)[-1].payload
    assert failed["error_type"] == "MAX_REVISIONS_EXCEEDED" and failed["failed_stage"] == "guardian"
    assert (failed["revision_count"], failed["max_revisions"]) == (2, 2)
    assert failed["feedback"] == ["architecture: add deployment detail"]           # Guardian feedback not hidden
    assert failed["requested_changes"] == ["Add a deployment task", "Add test tasks"]
    assert [r.status for r in revisions_of(db_session, run_id)] == ["needs_revision", "needs_revision"]
    st = client.get(f"/api/v1/workflow/{run_id}/status").json()
    assert st["status"] == "failed" and st["is_completed"] is False and st["failure"]["error_type"] == "MAX_REVISIONS_EXCEEDED"


def test_max_revisions_zero_disables_the_loop(scheduler, bus, run_id, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REVISIONS", 0)
    fakes.VERDICT[:] = ["needs_revision"]
    pump(scheduler, bus)
    assert "builder_revision" not in fakes.CALLS and revisions_of(db_session, run_id) == []
    assert events_of(db_session, run_id)[-1].payload["error_type"] == "MAX_REVISIONS_EXCEEDED"


def test_5_rejected_fails_without_any_revision(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["rejected"]
    pump(scheduler, bus)
    assert types_of(db_session, run_id) == FIRST + ["run.failed"]
    assert events_of(db_session, run_id)[-1].payload["error_type"] == "ReviewRejected"
    assert revisions_of(db_session, run_id) == [] and "builder_revision" not in fakes.CALLS
    assert status(db_session, run_id) == "failed"


def test_rejected_during_a_revision_is_recorded_on_that_revision(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision", "rejected"]
    pump(scheduler, bus)
    assert [(r.revision_number, r.status) for r in revisions_of(db_session, run_id)] == [(1, "rejected")]
    assert status(db_session, run_id) == "failed"


def test_run_is_never_completed_while_a_revision_is_pending(scheduler, bus, run_id, db_session, client):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    seen = []
    i = 0
    while i < len(bus.published):  # process one event at a time and inspect the state in between
        scheduler.process(KafkaEvent.model_validate_json(bus.published[i].to_json_bytes()))
        i += 1
        st = client.get(f"/api/v1/workflow/{run_id}/status").json()
        seen.append((st["status"], st["revision_status"], st["current_stage"]))
    assert ("running", "requested", "revision.requested") in seen   # verdict processed: revision row exists, Builder pending
    assert ("running", "revised", "tasks.generated") in seen        # Builder revised, Guardian re-review pending
    assert ("running", "revised", "review.completed") in seen       # re-review event pending
    assert all(s[0] == "running" for s in seen[:-1]) and seen[-1][0] == "completed"
    assert seen[-1][1] == "approved"


# ── invalid Guardian output ─────────────────────────────────────────────


@pytest.mark.parametrize("bad_report", [
    None, {}, {"overall_verdict": "maybe"}, {"summary": "no verdict"},
])
def test_invalid_guardian_output_fails_the_run_instead_of_looping(scheduler, bus, run_id, db_session, bad_report):
    ev = KafkaEvent(event_type="review.completed", source="guardian", run_id=run_id,
                    payload={"goal": "g", "validation_report": bad_report, "revision_number": 0})
    scheduler.process(ev)
    pump(scheduler, bus, start=1)  # deliver the resulting run.failed
    assert status(db_session, run_id) == "failed"
    assert not any(e.event_type == "revision.requested" for e in bus.published)


# ── idempotency ─────────────────────────────────────────────────────────


def test_duplicate_review_completed_creates_one_revision_request(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    review = run_until_published(scheduler, bus, "review.completed")
    scheduler.process(review)
    before = [e.event_type for e in bus.published]
    scheduler.process(review)  # redelivery of the very same review.completed
    scheduler.process(review)
    assert [e.event_type for e in bus.published] == before
    assert before.count("revision.requested") == 1 and len(revisions_of(db_session, run_id)) == 1


def test_duplicate_revision_requested_runs_builder_once(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    pump(scheduler, bus)
    req = next(e for e in bus.published if e.event_type == "revision.requested")
    for _ in range(3):
        scheduler.process(req)  # redeliveries after the run finished
    assert fakes.CALLS.count("builder_revision") == 1
    assert tasks_by_revision(db_session, run_id) == {0: 2, 1: 3} and len(revisions_of(db_session, run_id)) == 1


def test_duplicate_revision_requested_before_completion_is_skipped_by_event_id(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    review = run_until_published(scheduler, bus, "review.completed")
    scheduler.process(review)
    req = next(e for e in bus.published if e.event_type == "revision.requested")
    scheduler.process(req)  # Builder revision runs (first delivery)
    scheduler.process(req)  # duplicate, run still in progress
    scheduler.process(req)
    assert fakes.CALLS.count("builder_revision") == 1
    assert sum(e.event_type == "tasks.generated" and e.payload["revision_number"] == 1 for e in bus.published) == 1
    assert tasks_by_revision(db_session, run_id) == {0: 2, 1: 3} and status(db_session, run_id) == "running"


def test_duplicate_terminal_event_does_not_touch_the_run_twice(scheduler, bus, run_id, db_session):
    pump(scheduler, bus)
    done = next(e for e in bus.published if e.event_type == "run.completed")
    db_session.expire_all()
    duration = db_session.get(Run, run_id).duration_ms
    scheduler.process(done)
    db_session.expire_all()
    assert db_session.get(Run, run_id).duration_ms == duration and types_of(db_session, run_id).count("run.completed") == 1


def test_crash_before_commit_republishes_the_same_revision_identity(scheduler, bus, run_id, db_session):
    """Crash after publishing revision.requested but before the DB commit: the retry re-derives the SAME
    event_id and revision_id, so the consumer dedups it and only one revision row can exist."""
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    review = run_until_published(scheduler, bus, "review.completed")
    scheduler.process(review)
    first_req = next(e for e in bus.published if e.event_type == "revision.requested")
    (rev,) = revisions_of(db_session, run_id)
    rev_id = rev.id

    # what a crash between publish and commit leaves behind: the message was sent, the transaction rolled back
    db_session.execute(text("DELETE FROM run_revisions WHERE run_id = :r"), {"r": run_id})
    db_session.execute(text("DELETE FROM events WHERE id = :e"), {"e": str(review.event_id)})
    db_session.commit()
    scheduler.process(review)  # Kafka redelivers review.completed

    reqs = [e for e in bus.published if e.event_type == "revision.requested"]
    assert len(reqs) == 2 and reqs[1].event_id == first_req.event_id           # same event id -> consumer dedups it
    assert reqs[1].payload["revision"]["revision_id"] == rev_id                # same revision identity
    assert [r.id for r in revisions_of(db_session, run_id)] == [rev_id]        # exactly one row again
    scheduler.process(first_req)
    scheduler.process(reqs[1])  # the duplicate copy on the topic
    assert fakes.CALLS.count("builder_revision") == 1


# ── stale / inconsistent state ──────────────────────────────────────────


def test_stale_revision_events_are_ignored(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision"]
    i = 0
    while i < len(bus.published):
        scheduler.process(KafkaEvent.model_validate_json(bus.published[i].to_json_bytes()))
        i += 1
        if len(revisions_of(db_session, run_id)) == 1 and any(e.event_type == "revision.requested" for e in bus.published):
            break
    guardian_calls = fakes.CALLS.count("guardian")
    tasks_evt = next(e for e in bus.published if e.event_type == "tasks.generated")  # revision 0 output
    stale = KafkaEvent(event_type="tasks.generated", source="builder", run_id=run_id, payload=tasks_evt.payload)  # NEW id
    scheduler.process(stale)
    assert fakes.CALLS.count("guardian") == guardian_calls  # Guardian never reviews the superseded revision-0 output
    assert status(db_session, run_id) == "running"


def test_event_ahead_of_recorded_state_fails_the_run_loudly(scheduler, bus, run_id, db_session):
    base = {"goal": "g", "architecture_plan": {}, "research_report": {}, "task_graph": {}, "revision_number": 5}
    scheduler.process(KafkaEvent(event_type="tasks.generated", source="builder", run_id=run_id, payload=base))
    failed = events_of(db_session, run_id)
    assert status(db_session, run_id) == "running"  # run.failed was published, consumed next
    pump(scheduler, bus, start=1)
    assert status(db_session, run_id) == "failed"
    assert "inconsistent" in [e for e in events_of(db_session, run_id) if e.event_type == "run.failed"][0].payload["message"]


# ── failures during a revision ──────────────────────────────────────────


def test_builder_failure_during_revision_fails_the_run_and_marks_the_revision(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    fakes.FAIL_STAGE.append("builder_revision")
    pump(scheduler, bus)
    assert status(db_session, run_id) == "failed"
    failed = [e for e in events_of(db_session, run_id) if e.event_type == "run.failed"][0].payload
    assert failed["failed_stage"] == "builder" and "builder_revision exploded" in failed["message"]
    assert [r.status for r in revisions_of(db_session, run_id)] == ["failed"]
    assert fakes.CALLS.count("guardian") == 1 and tasks_by_revision(db_session, run_id) == {0: 2}


def test_guardian_failure_during_re_review_fails_the_run(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    fakes.FAIL_STAGE.append("guardian#2")
    pump(scheduler, bus)
    assert status(db_session, run_id) == "failed"
    failed = [e for e in events_of(db_session, run_id) if e.event_type == "run.failed"][0].payload
    assert failed["failed_stage"] == "guardian" and "guardian exploded" in failed["message"]
    assert [r.status for r in revisions_of(db_session, run_id)] == ["revised"] or \
           [r.status for r in revisions_of(db_session, run_id)] == ["failed"]
    assert [r.status for r in revisions_of(db_session, run_id)] == ["failed"]


def test_publish_failure_of_revision_requested_leaves_no_revision_state(scheduler, bus, run_id, db_session):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    bus.fail_types = {"revision.requested"}
    with pytest.raises(RuntimeError, match="kafka unavailable"):
        pump(scheduler, bus)
    assert status(db_session, run_id) == "running"  # a broker error is retried, it never fails the run
    assert revisions_of(db_session, run_id) == [] and "builder_revision" not in fakes.CALLS  # nothing half-committed
    bus.fail_types = set()
    scheduler.process(bus.published[-1])  # redelivery of the review.completed that could not be answered
    pump(scheduler, bus, start=len(bus.published) - 1)
    assert status(db_session, run_id) == "completed" and len(revisions_of(db_session, run_id)) == 1


# ── schema guarantees ───────────────────────────────────────────────────


def test_database_enforces_one_row_per_revision_number_and_valid_status(db_session, scheduler, bus, run_id):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    pump(scheduler, bus)
    (rev,) = revisions_of(db_session, run_id)
    dup = text("INSERT INTO run_revisions (id, run_id, revision_number, source_review_event_id, reason, feedback, "
               "requested_changes, status, created_at) VALUES (:id, :r, :n, 'x', 'y', '[]', '[]', :s, now())")
    with pytest.raises(Exception, match="uq_run_revisions_run_number"):
        db_session.execute(dup, {"id": "other-id", "r": run_id, "n": 1, "s": "requested"})
    db_session.rollback()
    with pytest.raises(Exception, match="ck_run_revisions_status"):
        db_session.execute(dup, {"id": "other-id", "r": run_id, "n": 9, "s": "bogus"})
    db_session.rollback()
    assert rev.revision_number == 1


# ── real Builder / Guardian workflows with a scripted LLM ───────────────


def _builder_inputs():
    from agents.architect.schemas import ArchitecturePlan
    from agents.builder.schemas import TaskGraph
    from agents.scout.schemas import ResearchReport
    rid = "00000000-0000-0000-0000-0000000000aa"
    plan = ArchitecturePlan.model_validate({"workflow_run_id": rid, "goal": "g", **fakes.PLAN})
    research = ResearchReport.model_validate({"workflow_run_id": rid, "goal": "g", **fakes.RESEARCH})
    prev = TaskGraph.model_validate({"workflow_run_id": rid, "goal": "g", **fakes.TASKS})
    return rid, plan, research, prev


@pytest.mark.anyio
async def test_builder_revision_prompt_carries_feedback_previous_tasks_and_revision_rules(monkeypatch):
    from uuid import UUID
    import agents.builder.service as bs
    llm = fakes.ScriptedLLM(dict(fakes.REPLIES))
    monkeypatch.setattr(bs, "get_llm", lambda: llm)
    rid, plan, research, prev = _builder_inputs()
    req = build_revision_request(report(), rid, "review-evt", 1, 3)

    graph = await bs.BuilderService().revise_task_graph(UUID(rid), "g", plan, research, prev, req)

    assert len(graph.tasks) == 3                                     # same output schema, validated as usual
    assert len(llm.prompts) == 1                                     # no wasted "analysis" call for a revision
    p = llm.prompts[0]
    assert "REVISION (revision 1)" in p and "Preserve valid work" in p and "Do not introduce unrelated changes" in p
    assert "- architecture: No deployment topology" in p and "- Add a deployment task" in p
    assert "1. T1 [depends on: -]" in p and "3. T3 [depends on: 2]" in p   # previous task graph rendered


@pytest.mark.anyio
async def test_builder_first_pass_is_unchanged_by_the_revision_feature(monkeypatch):
    from uuid import UUID
    import agents.builder.service as bs
    llm = fakes.ScriptedLLM(dict(fakes.REPLIES))
    monkeypatch.setattr(bs, "get_llm", lambda: llm)
    rid, plan, research, _ = _builder_inputs()
    await bs.BuilderService().generate_task_graph(UUID(rid), "g", plan, research)
    assert len(llm.prompts) == 2 and not any("REVISION" in p for p in llm.prompts)  # analysis + generation


@pytest.mark.anyio
async def test_guardian_reviews_the_actual_tasks_and_re_review_gets_the_previous_requests(monkeypatch):
    from uuid import UUID
    import agents.guardian.service as gs
    llm = fakes.ScriptedLLM(dict(fakes.REPLIES))
    monkeypatch.setattr(gs, "get_llm", lambda: llm)
    rid, plan, research, graph = _builder_inputs()

    first = await gs.GuardianService().generate_review(UUID(rid), "g", plan, research, graph)
    assert first.overall_verdict == "approved"
    assert not any("RE-REVIEW" in p for p in llm.prompts)                      # original review: no revision context
    assert all("3. T3 [depends on: 2]" in p for p in llm.prompts)              # Guardian sees the task list, not just a summary

    llm.prompts.clear()
    await gs.GuardianService().generate_review(UUID(rid), "g", plan, research, graph, revision_number=2,
                                               previous_requested_changes=["Add a deployment task"])
    review_prompt = next(p for p in llm.prompts if "RE-REVIEW of revision 2" in p)
    assert "- Add a deployment task" in review_prompt
