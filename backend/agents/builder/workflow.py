import logging
import time
from uuid import UUID

from agents.llm.interface import LLMClient
from llama_index.core.prompts import PromptTemplate
from llama_index.core.workflow import (
    Context,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)

from agents.base.retry import with_retry
from agents.base.validation import validate_min_max_count, validate_non_empty, validate_sequential_ids
from agents.builder.events import (
    ResearchReceivedEvent,
    InputsAnalyzedEvent,
    TaskGraphGeneratedEvent,
)
from agents.builder.exceptions import (
    TaskGraphGenerationError,
    TaskGraphValidationError,
)
from agents.builder.prompts import BUILDER_ANALYSIS_PROMPT, BUILDER_REVISION_PROMPT, BUILDER_TASK_PROMPT
from agents.builder.schemas import LLMTaskGraph, TaskGraph
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import ResearchReport

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
MIN_TASKS = 2
MAX_TASKS = 30


def format_tasks(graph: TaskGraph | None) -> str:
    """Compact, deterministic rendering of a task graph for prompts (Builder revision / Guardian review)."""
    if graph is None:
        return "(none)"
    lines = [f"Summary: {graph.summary}"]
    for t in graph.tasks:
        deps = ", ".join(str(d) for d in t.dependencies) or "-"
        lines.append(f"{t.id}. {t.title} [depends on: {deps}] - {t.description[:240]}")
        if t.acceptance_criteria:
            lines.append("   acceptance: " + "; ".join(c[:120] for c in t.acceptance_criteria))
    return "\n".join(lines)


class BuilderWorkflow(Workflow):

    def __init__(self, llm: LLMClient, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm

    # ── Step 1: Receive inputs ───────────────────────────────

    @step
    async def receive_inputs(
        self,
        ctx: Context,
        ev: StartEvent,
    ) -> ResearchReceivedEvent:
        data = ev.to_dict()
        workflow_run_id: UUID = data["workflow_run_id"]
        goal: str = data["goal"]
        plan: ArchitecturePlan = data["architecture_plan"]
        report: ResearchReport = data["research_report"]
        revision = data.get("revision")  # RevisionRequest when this is a Guardian-requested revision
        await ctx.store.set("revision", revision)
        await ctx.store.set("previous_graph", data.get("previous_graph"))
        if revision is not None:
            logger.info("[Builder] Builder revision started | run=%s | revision=%d",
                        workflow_run_id, revision.revision_number)

        logger.info(
            "[Builder] receive_inputs | run=%s | components=%d | findings=%d",
            workflow_run_id, len(plan.components), len(report.findings),
        )

        return ResearchReceivedEvent(
            workflow_run_id=workflow_run_id,
            goal=goal,
            architecture_plan=plan,
            research_report=report,
        )

    # ── Step 2: Analyze inputs ───────────────────────────────

    @step
    async def analyze_inputs(
        self,
        ctx: Context,
        ev: ResearchReceivedEvent,
    ) -> InputsAnalyzedEvent:
        if await ctx.store.get("revision", default=None) is not None:
            # A revision is driven by the Guardian's feedback, not a fresh analysis: skip the extra LLM call.
            return InputsAnalyzedEvent(
                workflow_run_id=ev.workflow_run_id, goal=ev.goal,
                architecture_plan=ev.architecture_plan, research_report=ev.research_report,
            )

        start = time.monotonic()
        plan = ev.architecture_plan
        report = ev.research_report

        plan_components = "\n".join(
            [f"- {c.name} ({c.layer}): {c.description}" for c in plan.components]
        )

        prompt = PromptTemplate(BUILDER_ANALYSIS_PROMPT)
        analysis_text = await self.llm.complete(
            prompt.format(
                architecture_summary=plan.summary,
                architecture_components=plan_components,
                research_summary=report.summary,
            )
        )

        await ctx.store.set("builder_analysis", analysis_text)

        duration = time.monotonic() - start
        logger.info(
            "[Builder] analyze_inputs | run=%s | duration=%.2fs",
            ev.workflow_run_id, duration,
        )

        return InputsAnalyzedEvent(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            architecture_plan=ev.architecture_plan,
            research_report=ev.research_report,
        )

    # ── Step 3: Generate task graph ──────────────────────────

    @step
    async def generate_task_graph(
        self,
        ctx: Context,
        ev: InputsAnalyzedEvent,
    ) -> TaskGraphGeneratedEvent:
        plan = ev.architecture_plan
        report = ev.research_report
        
        plan_components = "\n".join(
            [f"- {c.name} ({c.layer}): {c.description}" for c in plan.components]
        )

        revision = await ctx.store.get("revision", default=None)
        previous = await ctx.store.get("previous_graph", default=None)
        if revision is None:
            base_prompt = BUILDER_TASK_PROMPT
            extra = {}
        else:
            base_prompt = BUILDER_REVISION_PROMPT
            extra = dict(
                revision_number=revision.revision_number,
                previous_tasks=format_tasks(previous),
                feedback="\n".join(f"- {f}" for f in revision.feedback),
                requested_changes="\n".join(f"- {c}" for c in revision.requested_changes),
            )

        try:
            llm_graph = await with_retry(
                llm=self.llm,
                output_cls=LLMTaskGraph,
                base_prompt=base_prompt,
                max_retries=MAX_RETRIES,
                agent_name="Builder",
                run_id=str(ev.workflow_run_id),
                architecture_summary=plan.summary,
                architecture_components=plan_components,
                research_summary=report.summary,
                **extra,
            )
            
            return TaskGraphGeneratedEvent(
                workflow_run_id=ev.workflow_run_id,
                goal=ev.goal,
                llm_task_graph=llm_graph,
            )
        except Exception as e:
            raise TaskGraphGenerationError(str(e)) from e

    # ── Step 4: Validate task graph ──────────────────────────

    @step
    async def validate_task_graph(
        self,
        ctx: Context,
        ev: TaskGraphGeneratedEvent,
    ) -> StopEvent:
        llm_graph = ev.llm_task_graph
        errors: list[str] = []

        if err := validate_non_empty(llm_graph.summary, "Summary"):
            errors.append(err)
            
        if err := validate_min_max_count(llm_graph.tasks, MIN_TASKS, MAX_TASKS, "tasks"):
            errors.append(err)

        if err := validate_sequential_ids(llm_graph.tasks):
            errors.append(f"Task {err}")

        # Validate task dependencies
        task_ids = [t.id for t in llm_graph.tasks]
        for task in llm_graph.tasks:
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    errors.append(f"Task {task.id} depends on unknown task {dep_id}.")
                elif dep_id >= task.id:
                    errors.append(f"Task {task.id} depends on task {dep_id}, which is not earlier in execution order.")
                    
            if task.assigned_agent not in ["developer_agent"]:
                errors.append(f"Task {task.id} assigned to invalid agent {task.assigned_agent}.")

        if errors:
            raise TaskGraphValidationError(f"Task graph validation failed: {'; '.join(errors)}")

        graph = TaskGraph(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            summary=llm_graph.summary,
            tasks=llm_graph.tasks,
        )

        logger.info(
            "[Builder] validate_task_graph | run=%s | tasks=%d | PASSED",
            graph.workflow_run_id, len(graph.tasks),
        )

        return StopEvent(result=graph)
