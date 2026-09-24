"""
Phase 5 — concurrency and seeded stress. Many runs share one scheduler/log; random crashes and duplicate
deliveries are injected; afterwards every DB invariant must hold and every run must be in the expected state.
The seed is printed on failure (re-run with STRESS_SEED=<n>) so a failure is reproducible.
"""

import os
import random

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import Task
from tests import scenario_agents as sa
from tests.invariants import check_invariants
from tests.minikafka import Harness, MiniKafka
from tests.test_reliability_kafka import state, submit

SEED = int(os.environ.get("STRESS_SEED", "20260924"))
POINTS = ["before_publish", "after_publish", "at_commit", "after_db_commit"]
TYPES = ["run.created", "strategy.created", "architecture.created", "research.completed", "tasks.generated",
         "review.completed", "revision.requested"]


@pytest.fixture(autouse=True)
def agents(monkeypatch):
    sa.install(monkeypatch)


def expected(goal: str) -> str:
    sp = sa.spec(goal)
    if sp["fail"] or sp["timeout"]:
        return "failed"
    v = sp["v"]
    if "rejected" in v[:settings.MAX_REVISIONS + 1] and all(x != "approved" for x in v[:v.index("rejected") + 1]):
        return "failed"
    if v[0] == "approved" or "approved" in v[:settings.MAX_REVISIONS + 1]:
        return "completed"
    return "failed"  # never approved within MAX_REVISIONS


def test_ten_concurrent_runs_are_isolated(session_factory):
    h = Harness(session_factory)
    goals, rids = {}, {}
    for i in range(10):
        verdicts = ["approved", "needs,approved", "needs,needs,approved"][i % 3]
        goals[i] = f"tag=c{i} v={verdicts}"
        rids[i] = submit(h, session_factory, goals[i], project=f"proj{i % 4}")
    h.run_until_done(timeout=120)
    for i, rid in rids.items():
        assert state(session_factory, rid)[0] == "completed"
    with session_factory() as db:
        assert check_invariants(db, max_revisions=settings.MAX_REVISIONS) == []
        for t in db.scalars(select(Task)):  # no task leaked into another run
            assert t.title.startswith(sa.spec(goals[[i for i, r in rids.items() if r == t.run_id][0]])["tag"] + " ")


@pytest.mark.parametrize("seed", [SEED])
def test_fifty_run_seeded_stress_with_random_crashes_and_duplicates(session_factory, seed):
    rng = random.Random(seed)

    class Dup(MiniKafka):  # ~15% of published events are delivered twice
        def append(self, raw):
            i = super().append(raw)
            if rng.random() < 0.15:
                super().append(raw)
            return i

    h = Harness(session_factory, kafka=Dup())
    goals = {}
    for i in range(50):
        v = rng.choice(["approved", "needs,approved", "needs,needs,approved", "needs", "rejected", "needs,rejected"])
        extra = rng.choice(["", "", "", "fail=architect", "fail=builder", "timeout=scout", "fail=guardian",
                            "fail=builder_revision"])
        goal = f"tag=s{i} v={v} {extra}".strip()
        goals[submit(h, session_factory, goal, project=f"proj{i % 5}")] = goal
    for _ in range(12):
        h.hooks.arm(rng.choice(POINTS), rng.choice(TYPES), nth=rng.randint(1, 30))
    crashes = h.run_until_done(max_restarts=40, timeout=300)

    with session_factory() as db:
        violations = check_invariants(db, max_revisions=settings.MAX_REVISIONS)
    assert violations == [], f"seed={seed} crashes={crashes}\n" + "\n".join(violations[:20])
    for rid, goal in goals.items():
        got, types = state(session_factory, rid)
        assert got in ("completed", "failed"), (seed, goal, types)
        if "builder_revision" in goal and "needs" not in goal:
            continue
        assert got == expected(goal), (seed, goal, got, types)
    # an agent is only ever re-executed because a crash interrupted its transaction: bounded by the crash count
    reruns = sum(max(0, n - (2 if s == "guardian" else 1)) for (_, s), n in sa.EXEC.items() if s != "guardian") \
        + sum(max(0, n - (settings.MAX_REVISIONS + 1)) for (_, s), n in sa.EXEC.items() if s == "guardian")
    assert reruns <= crashes + 12, (reruns, crashes)


def test_memory_and_projects_stay_isolated_under_concurrency(session_factory):
    h = Harness(session_factory)
    for i in range(6):
        submit(h, session_factory, f"tag=iso{i} v=needs,approved", project=f"proj{i % 3}")
    h.run_until_done(timeout=120)
    with session_factory() as db:
        assert check_invariants(db, max_revisions=settings.MAX_REVISIONS) == []
