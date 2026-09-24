"""
Database invariant checker for the reliability / stress suites. Returns human-readable violations (empty = healthy).

Invariants (matched to the real schema and event lifecycle):
  I1  no duplicate event ids                                   (also enforced by the events PK)
  I2  no orphan events / tasks / revisions / memories          (also enforced by foreign keys)
  I3  event lifecycle is a valid prefix of
        run.created strategy.created architecture.created research.completed tasks.generated review.completed
        (revision.requested tasks.generated review.completed)*   then at most ONE terminal event, last
  I4  runs.status = completed  =>  exactly one run.completed, no run.failed, last review verdict approved
      runs.status = failed     =>  exactly one run.failed, no run.completed
      runs.status = running    =>  (quiesced systems only) violation: a stuck run
  I5  revision numbers per run are contiguous 1..k, k <= MAX_REVISIONS
  I6  every revision row has its source review.completed event; tasks/review event ids it references exist
  I7  no revision left 'requested'/'revised' on a terminal run; a completed run's last revision is 'approved'
  I8  tasks: revision_number 0..k only, one set per revision, a completed run has a task set for every revision,
      and no orphan task set (revision > 0 without a revision row)
  I9  every revision.requested event has exactly one revision row (same revision number)
  I10 no cross-run contamination: task titles / event goals carry the owning run's tag (when goals use tag=...)
  I11 no cross-project memories: a memory's project equals the project of the run that wrote it
"""

import re
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AgentMemory, Event, Run, RunRevision, Task

FIRST = ["run.created", "strategy.created", "architecture.created", "research.completed", "tasks.generated",
         "review.completed"]
CYCLE = ["revision.requested", "tasks.generated", "review.completed"]
TERMINAL = ("run.completed", "run.failed")


def _ideal(n: int) -> list[str]:
    seq = list(FIRST)
    while len(seq) < n:
        seq += CYCLE
    return seq[:n]


def lifecycle_violation(types: list[str]) -> str | None:
    body = list(types)
    if body and body[-1] in TERMINAL:
        body = body[:-1]
    if any(t in TERMINAL for t in body):
        return f"terminal event not last / more than one terminal event: {types}"
    if body != _ideal(len(body)):
        return f"invalid lifecycle {types}"
    return None


def tag_of(goal: str) -> str | None:
    m = re.search(r"\btag=(\S+)", goal or "")
    return m.group(1) if m else None


def check_invariants(db: Session, *, max_revisions: int, expect_quiesced: bool = True) -> list[str]:
    v: list[str] = []
    db.expire_all()
    runs = {r.id: r for r in db.scalars(select(Run))}
    events: dict[str, list[Event]] = defaultdict(list)
    for e in db.scalars(select(Event).order_by(Event.created_at, Event.id)):
        events[e.run_id].append(e)
    revs: dict[str, list[RunRevision]] = defaultdict(list)
    for r in db.scalars(select(RunRevision).order_by(RunRevision.revision_number)):
        revs[r.run_id].append(r)
    tasks: dict[str, list[Task]] = defaultdict(list)
    for t in db.scalars(select(Task)):
        tasks[t.run_id].append(t)

    # I1
    for eid, n in db.execute(select(Event.id, func.count()).group_by(Event.id).having(func.count() > 1)):
        v.append(f"I1 duplicate event id {eid} x{n}")
    # I2
    for label, ids in (("events", events), ("tasks", tasks), ("revisions", revs)):
        for rid in ids:
            if rid not in runs:
                v.append(f"I2 orphan {label} for missing run {rid}")
    all_event_ids = {e.id for evs in events.values() for e in evs}

    for rid, run in runs.items():
        evs = events.get(rid, [])
        types = [e.event_type for e in evs]
        # I3
        if (msg := lifecycle_violation(types)) is not None:
            v.append(f"I3 run {rid}: {msg}")
        # I4
        completed, failed = types.count("run.completed"), types.count("run.failed")
        if run.status == "completed":
            if completed != 1 or failed:
                v.append(f"I4 run {rid} is completed but has run.completed x{completed}, run.failed x{failed}")
            reviews = [e for e in evs if e.event_type == "review.completed"]
            verdict = ((reviews[-1].payload or {}).get("validation_report") or {}).get("overall_verdict") if reviews else None
            if verdict != "approved":
                v.append(f"I4 run {rid} is completed but the last review verdict is {verdict!r}")
            if run.duration_ms is None:
                v.append(f"I4 run {rid} is completed without duration_ms")
        elif run.status == "failed":
            if failed < 1 or completed:
                v.append(f"I4 run {rid} is failed but has run.failed x{failed}, run.completed x{completed}")
            if failed > 1:
                v.append(f"I4 run {rid} has {failed} run.failed events")
        elif run.status == "running":
            if expect_quiesced:
                v.append(f"I4 run {rid} is STUCK in 'running' (events: {types})")
        else:
            v.append(f"I4 run {rid} has invalid status {run.status!r}")

        rr = revs.get(rid, [])
        numbers = [r.revision_number for r in rr]
        # I5
        if numbers != list(range(1, len(numbers) + 1)):
            v.append(f"I5 run {rid} revision numbers not contiguous from 1: {numbers}")
        if len(numbers) > max_revisions:
            v.append(f"I5 run {rid} has {len(numbers)} revisions > MAX_REVISIONS={max_revisions}")
        # I6 / I9
        requested = [e for e in evs if e.event_type == "revision.requested"]
        by_number = {r.revision_number: r for r in rr}
        for r in rr:
            if r.source_review_event_id not in all_event_ids:
                v.append(f"I6 revision {rid}#{r.revision_number}: source review event {r.source_review_event_id} missing")
            for label, ref in (("tasks_event_id", r.tasks_event_id), ("review_event_id", r.review_event_id)):
                if ref is not None and ref not in all_event_ids:
                    v.append(f"I6 revision {rid}#{r.revision_number}: {label} {ref} does not exist")
        req_numbers = sorted((e.payload or {}).get("revision_number") for e in requested)
        if len(req_numbers) != len(set(req_numbers)):
            v.append(f"I9 run {rid}: duplicate revision.requested for {req_numbers}")
        for n in req_numbers:
            if n not in by_number:
                v.append(f"I9 run {rid}: revision.requested for #{n} has no revision row")
        # I7
        if run.status in ("completed", "failed"):
            for r in rr:
                if r.status in ("requested", "revised"):
                    v.append(f"I7 run {rid} is {run.status} but revision #{r.revision_number} is still {r.status!r}")
        if run.status == "completed" and rr and rr[-1].status != "approved":
            v.append(f"I7 run {rid} completed but its last revision is {rr[-1].status!r}")
        # I8
        ts = tasks.get(rid, [])
        by_rev: dict[int, int] = defaultdict(int)
        for t in ts:
            by_rev[t.revision_number] += 1
        for n in by_rev:
            if n != 0 and n not in by_number:
                v.append(f"I8 run {rid} has an orphan task set for revision {n} (no revision row)")
            if n > len(numbers):
                v.append(f"I8 run {rid} has tasks for revision {n} but only {len(numbers)} revision rows")
        if run.status == "completed":
            for n in range(0, len(numbers) + 1):
                if by_rev.get(n, 0) == 0:
                    v.append(f"I8 completed run {rid} has no task set for revision {n}")
        # I10 (only when the goal carries a tag=...)
        tag = tag_of(run.goal)
        if tag:
            for t in ts:
                if not (t.title or "").startswith(tag + " "):
                    v.append(f"I10 run {rid} (tag {tag}) owns a task titled {t.title!r}")
            for e in evs:
                g = (e.payload or {}).get("goal")
                if g is not None and g != run.goal:
                    v.append(f"I10 event {e.id} of run {rid} carries another run's goal {g!r}")

    # I11
    for m in db.scalars(select(AgentMemory)):
        if m.run_id is not None:
            run = runs.get(m.run_id)
            if run is None:
                v.append(f"I2 orphan memory {m.id} (run {m.run_id})")
            elif run.project_id != m.project_id:
                v.append(f"I11 memory {m.id} of project {m.project_id} was written by run {m.run_id} of project {run.project_id}")
    return v
