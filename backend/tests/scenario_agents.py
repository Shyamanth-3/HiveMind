"""
Goal-driven deterministic agents for reliability tests. The run's GOAL encodes what the agents do, so many runs
with different behavior can execute at once (concurrency / stress) with no global switches:

    "tag=r17 v=needs,needs,approved fail=scout timeout=guardian delay=0.01"

  tag      marker copied into every task title (proves no cross-run contamination)
  v        Guardian verdict per revision number (index 0 = original output); the last one repeats
  fail     stage that raises RuntimeError      (queen|architect|scout|builder|builder_revision|guardian)
  timeout  stage that raises TimeoutError      (what a workflow timeout looks like to the scheduler)
  delay    seconds each agent "works"

Every execution and every successful completion is counted per (run_id, stage) in EXEC / DONE.
"""

import re
import threading
import time
from collections import Counter
from uuid import UUID

from agents.architect.schemas import ArchitecturePlan
from agents.builder.schemas import TaskGraph, TaskNode
from agents.guardian.schemas import ValidationReport
from agents.queen.schemas import Strategy
from agents.scout.schemas import ResearchReport
from tests import fakes

_LOCK = threading.Lock()
EXEC: Counter = Counter()   # (run_id, stage) -> times the agent started
DONE: Counter = Counter()   # (run_id, stage) -> times it returned a result
VERDICT_ALIASES = {"needs": "needs_revision", "approved": "approved", "rejected": "rejected", "maybe": "maybe"}


def reset() -> None:
    with _LOCK:
        EXEC.clear()
        DONE.clear()


def spec(goal: str) -> dict:
    kv = dict(re.findall(r"(\w+)=([^\s]+)", goal))
    return {
        "tag": kv.get("tag", "t"),
        "v": [VERDICT_ALIASES[x] for x in kv.get("v", "approved").split(",")],
        "fail": kv.get("fail"), "timeout": kv.get("timeout"), "delay": float(kv.get("delay", "0")),
    }


def _enter(run_id, goal: str, stage: str) -> dict:
    sp = spec(goal)
    with _LOCK:
        EXEC[(str(run_id), stage)] += 1
    if sp["delay"]:
        time.sleep(sp["delay"])
    if sp["timeout"] == stage:
        raise TimeoutError(f"{stage} timed out (simulated)")
    if sp["fail"] == stage:
        raise RuntimeError(f"{stage} exploded (simulated)")
    return sp


def _done(run_id, stage: str) -> None:
    with _LOCK:
        DONE[(str(run_id), stage)] += 1


class SQueen(fakes.FakeQueen):
    async def generate_strategy(self, run_id: UUID, goal: str, project_id: str = "p", source_event_id=None) -> Strategy:
        _enter(run_id, goal, "queen")
        out = await super().generate_strategy(run_id, goal, project_id, source_event_id)
        _done(run_id, "queen")
        return out


class SArchitect(fakes.FakeArchitect):
    async def generate_plan(self, run_id, goal, strategy) -> ArchitecturePlan:
        _enter(run_id, goal, "architect")
        out = await super().generate_plan(run_id, goal, strategy)
        _done(run_id, "architect")
        return out


class SScout(fakes.FakeScout):
    async def generate_research(self, run_id, goal, plan) -> ResearchReport:
        _enter(run_id, goal, "scout")
        out = await super().generate_research(run_id, goal, plan)
        _done(run_id, "scout")
        return out


def _graph(run_id, goal: str, tag: str, n: int, count: int) -> TaskGraph:
    suffix = "" if n == 0 else f" (rev {n})"
    nodes = [TaskNode(id=i, title=f"{tag} Task {i}{suffix}", description="d", priority="high",
                      dependencies=[i - 1] if i > 1 else [], estimated_complexity="low", required_files=["a.py"],
                      acceptance_criteria=["ok"], assigned_agent="developer_agent") for i in range(1, count + 1)]
    return TaskGraph(workflow_run_id=run_id, goal=goal, summary=f"{tag} tasks rev {n}", tasks=nodes)


class SBuilder(fakes.FakeBuilder):
    async def generate_task_graph(self, run_id, goal, plan, report) -> TaskGraph:
        sp = _enter(run_id, goal, "builder")
        out = _graph(run_id, goal, sp["tag"], 0, 2)
        _done(run_id, "builder")
        return out

    async def revise_task_graph(self, run_id, goal, plan, report, previous_graph, revision) -> TaskGraph:
        sp = _enter(run_id, goal, "builder_revision")
        out = _graph(run_id, goal, sp["tag"], revision.revision_number, 3)
        _done(run_id, "builder_revision")
        return out


class SGuardian(fakes.FakeGuardian):
    async def generate_review(self, run_id, goal, plan, report, graph, revision_number=0,
                              previous_requested_changes=None) -> ValidationReport:
        sp = _enter(run_id, goal, "guardian")
        verdicts = sp["v"]
        verdict = verdicts[min(revision_number, len(verdicts) - 1)]
        needs = verdict != "approved"
        out = ValidationReport.model_construct(  # model_construct: lets tests inject an INVALID verdict like "maybe"
            workflow_run_id=run_id, goal=goal, summary=f"{sp['tag']} review says {verdict}", overall_verdict=verdict,
            architecture_review=fakes.ArchitectureReview(is_sound=not needs, feedback="add deployment detail" if needs else "ok"),
            dependency_review=fakes.DependencyReview(has_cycles=False, feedback="ok"),
            security_review=fakes.SecurityReview(is_secure=True, feedback="ok"),
            performance_review=fakes.PerformanceReview(is_performant=True, feedback="ok"),
            maintainability_review=fakes.MaintainabilityReview(is_maintainable=True, feedback="ok"),
            recommendations=["Add a deployment task", "Add test tasks"] if needs else [],
        )
        _done(run_id, "guardian")
        return out


def install(monkeypatch, queen=SQueen) -> None:
    from app.scheduler import consumer
    reset()
    for name, cls in [("QueenService", queen), ("ArchitectService", SArchitect), ("ScoutService", SScout),
                      ("BuilderService", SBuilder), ("GuardianService", SGuardian)]:
        monkeypatch.setattr(consumer, name, cls)
