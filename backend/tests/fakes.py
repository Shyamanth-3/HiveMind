"""Deterministic stand-ins for Kafka and the LLM-backed agent services. No network, no credits."""

import json
import re
from types import SimpleNamespace
from uuid import UUID

from agents.architect.schemas import ArchitecturePlan, Component, Dependency, Milestone, RiskAssessment
from agents.builder.schemas import TaskGraph, TaskNode
from agents.guardian.schemas import (
    ArchitectureReview, DependencyReview, MaintainabilityReview,
    PerformanceReview, SecurityReview, ValidationReport,
)
from agents.queen.schemas import Strategy, StrategyPhase
from agents.scout.schemas import ResearchFinding, ResearchReport
from app.events.event_bus import EventBus
from agents.llm.interface import LLMClient
from app.events.schemas import KafkaEvent


class FakeBus(EventBus):
    """Records published events. `fail_types` makes publish raise, like a Kafka outage."""

    def __init__(self):
        self.published: list[KafkaEvent] = []
        self.fail_types: set[str] = set()
        self.closed = False

    def publish(self, event: KafkaEvent) -> None:
        if event.event_type in self.fail_types:
            raise RuntimeError(f"kafka unavailable for {event.event_type}")
        self.published.append(event)

    def close(self) -> None:
        self.closed = True


CALLS: list[str] = []            # agent executions (entries, including ones that then failed), in order
FAIL_STAGE: list[str] = []       # "guardian" fails every call; "guardian#2" fails only the 2nd call
CRASH_ONCE: list[str] = []       # stage names that simulate a hard process crash (SystemExit) once
VERDICT = ["approved"]           # Guardian verdicts: each call pops the first; the last one repeats
GUARDIAN_INPUTS: list[dict] = []  # what each Guardian call reviewed: revision number + task titles
BUILDER_REVISIONS: list[dict] = []  # each COMPLETED Builder revision: what it was given
DELAY = [0.0]                    # seconds each fake agent "works" (lets tests act while a run is in progress)


def reset_fakes() -> None:
    CALLS.clear()
    FAIL_STAGE.clear()
    CRASH_ONCE.clear()
    DELAY[0] = 0.0
    VERDICT[:] = ["approved"]
    GUARDIAN_INPUTS.clear()
    BUILDER_REVISIONS.clear()


def _enter(stage: str) -> None:
    CALLS.append(stage)
    if DELAY[0]:
        import time
        time.sleep(DELAY[0])
    if stage in CRASH_ONCE:
        CRASH_ONCE.remove(stage)
        raise SystemExit(f"simulated crash in {stage}")  # BaseException: not caught by the scheduler's handler
    if stage in FAIL_STAGE or f"{stage}#{CALLS.count(stage)}" in FAIL_STAGE:
        raise RuntimeError(f"{stage} exploded")


class FakeQueen:
    async def generate_strategy(self, run_id: UUID, goal: str, project_id: str = "p", source_event_id=None) -> Strategy:
        _enter("queen")
        return Strategy(workflow_run_id=run_id, goal=goal, summary="s",
                        phases=[StrategyPhase(id=1, title="t", description="d")])


class FakeArchitect:
    async def generate_plan(self, run_id, goal, strategy) -> ArchitecturePlan:
        _enter("architect")
        return ArchitecturePlan(
            workflow_run_id=run_id, goal=goal, summary="plan",
            components=[Component(id="api", name="API", description="d", layer="backend")],
            dependencies=[Dependency(source_id="api", target_id="api", relationship="self")],
            execution_order=["api"],
            milestones=[Milestone(id="m1", title="m", description="d", components=["api"])],
            risk_assessment=[RiskAssessment(area="a", risk="r", severity="low", mitigation="m")],
        )


class FakeScout:
    async def generate_research(self, run_id, goal, plan) -> ResearchReport:
        _enter("scout")
        return ResearchReport(
            workflow_run_id=run_id, goal=goal, summary="research",
            findings=[ResearchFinding(topic="t", finding="f", source_type="x", relevance="r")],
            library_recommendations=[], security_considerations=[], performance_considerations=[],
        )


class FakeBuilder:
    async def generate_task_graph(self, run_id, goal, plan, report) -> TaskGraph:
        _enter("builder")

        def node(i, deps):
            return TaskNode(id=i, title=f"Task {i}", description="d", priority="high", dependencies=deps,
                            estimated_complexity="low", required_files=["a.py"],
                            acceptance_criteria=["works"], assigned_agent="developer_agent")

        return TaskGraph(workflow_run_id=run_id, goal=goal, summary="tasks", tasks=[node(1, []), node(2, [1])])


def _rev_graph(run_id, goal, n):
    def node(i, deps):
        return TaskNode(id=i, title=f"Task {i} (rev {n})", description="d", priority="high", dependencies=deps,
                        estimated_complexity="low", required_files=["a.py"],
                        acceptance_criteria=["works"], assigned_agent="developer_agent")

    return TaskGraph(workflow_run_id=run_id, goal=goal, summary=f"tasks rev {n}",
                     tasks=[node(1, []), node(2, [1]), node(3, [1, 2])])


async def _revise(self, run_id, goal, plan, report, previous_graph, revision) -> TaskGraph:
    _enter("builder_revision")
    BUILDER_REVISIONS.append({
        "revision": revision.revision_number, "feedback": list(revision.feedback),
        "requested_changes": list(revision.requested_changes),
        "previous_titles": [t.title for t in previous_graph.tasks],
    })
    return _rev_graph(run_id, goal, revision.revision_number)


FakeBuilder.revise_task_graph = _revise


class FakeGuardian:
    async def generate_review(self, run_id, goal, plan, report, graph, revision_number=0,
                              previous_requested_changes=None) -> ValidationReport:
        _enter("guardian")
        GUARDIAN_INPUTS.append({"revision": revision_number, "titles": [t.title for t in graph.tasks],
                                "previous": list(previous_requested_changes or [])})
        verdict = VERDICT.pop(0) if len(VERDICT) > 1 else VERDICT[0]
        needs = verdict != "approved"
        return ValidationReport(
            workflow_run_id=run_id, goal=goal, summary=f"review says {verdict}", overall_verdict=verdict,
            architecture_review=ArchitectureReview(is_sound=not needs, feedback="add deployment detail" if needs else "ok"),
            dependency_review=DependencyReview(has_cycles=False, feedback="ok"),
            security_review=SecurityReview(is_secure=True, feedback="ok"),
            performance_review=PerformanceReview(is_performant=True, feedback="ok"),
            maintainability_review=MaintainabilityReview(is_maintainable=True, feedback="ok"),
            recommendations=["Add a deployment task", "Add test tasks"] if needs else [],
        )


def install_fake_agents(monkeypatch) -> None:
    from app.scheduler import consumer
    reset_fakes()
    for name, fake in [("QueenService", FakeQueen), ("ArchitectService", FakeArchitect),
                       ("ScoutService", FakeScout), ("BuilderService", FakeBuilder),
                       ("GuardianService", FakeGuardian)]:
        monkeypatch.setattr(consumer, name, fake)


# ── scripted LLM + canned agent payloads (used by workflow-level tests) ──


class ScriptedLLM(LLMClient):
    """A provider-neutral LLM returning canned text. Structured calls are recognised by the schema title in the prompt."""

    provider, model = "scripted", "scripted-model"

    def __init__(self, replies: dict[str, object] | None = None):
        self.replies = replies or {}
        self.prompts: list[str] = []
        self.kwargs: list[dict] = []   # per call: {"json_mode": bool}

    async def _complete(self, prompt: str, json_mode: bool) -> str:
        self.prompts.append(prompt)
        self.kwargs.append({"json_mode": json_mode})
        # Pydantic puts the top-level schema title last (after $defs / properties)
        titles = (re.findall(r'"title": "(\w+)", "type": "object"', prompt.split("JSON Schema:")[-1])
                  if "JSON Schema:" in prompt else [])
        title = titles[-1] if titles else None
        reply = self.replies.get(title, "Free-text analysis.")
        if isinstance(reply, list):  # sequence of replies for repeated calls
            reply = reply.pop(0)
        return reply if isinstance(reply, str) else json.dumps(reply)



STRATEGY = {"summary": "s", "phases": [{"id": 1, "title": "Plan", "description": "d"},
                                       {"id": 2, "title": "Build", "description": "d"}]}
ANALYSIS = {"complexity": "medium", "estimated_phases": 3, "project_type": "web_app",
            "needs_research": False, "reasoning": "r"}
PLAN = {
    "summary": "plan",
    "components": [{"id": "api", "name": "API", "description": "d", "layer": "backend"},
                   {"id": "db", "name": "DB", "description": "d", "layer": "database"}],
    "dependencies": [{"source_id": "api", "target_id": "db", "relationship": "reads"}],
    "execution_order": ["db", "api"],
    "milestones": [{"id": "m1", "title": "m", "description": "d", "components": ["db"]}],
    "risk_assessment": [{"area": "a", "risk": "r", "severity": "low", "mitigation": "m"}],
}
RESEARCH = {
    "summary": "r",
    "findings": [{"topic": "t", "finding": "f", "source_type": "x", "relevance": "r"}],
    "library_recommendations": [], "security_considerations": [], "performance_considerations": ["cache"],
}
TASKS = {"summary": "t", "tasks": [
    {"id": i, "title": f"T{i}", "description": "d", "priority": "high", "dependencies": [i - 1] if i > 1 else [],
     "estimated_complexity": "low", "required_files": ["a.py"], "acceptance_criteria": ["ok"],
     "assigned_agent": "developer_agent"} for i in (1, 2, 3)]}
REVIEW = {
    "summary": "review", "overall_verdict": "approved",
    "architecture_review": {"is_sound": True, "feedback": "ok"},
    "dependency_review": {"has_cycles": False, "feedback": "ok"},
    "security_review": {"is_secure": True, "feedback": "ok"},
    "performance_review": {"is_performant": True, "feedback": "ok"},
    "maintainability_review": {"is_maintainable": True, "feedback": "ok"},
    "recommendations": [],
}
REPLIES = {"MemoryExtraction": {"memories": []}, "GoalAnalysis": ANALYSIS, "LLMStrategy": STRATEGY, "LLMArchitecturePlan": PLAN,
           "LLMResearchReport": RESEARCH, "LLMTaskGraph": TASKS, "LLMValidationReport": REVIEW}


