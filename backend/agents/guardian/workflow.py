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
from agents.base.validation import validate_non_empty
from agents.guardian.events import (
    InputsReceivedEvent,
    InputsAnalyzedEvent,
    ReviewGeneratedEvent,
)
from agents.guardian.exceptions import (
    ReviewGenerationError,
    ReviewValidationError,
)
from agents.guardian.prompts import GUARDIAN_ANALYSIS_PROMPT, GUARDIAN_REREVIEW_CONTEXT, GUARDIAN_REVIEW_PROMPT
from agents.guardian.schemas import LLMValidationReport, ValidationReport
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import ResearchReport
from agents.builder.schemas import TaskGraph
from agents.builder.workflow import format_tasks

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


class GuardianWorkflow(Workflow):

    def __init__(self, llm: LLMClient, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm

    # ── Step 1: Receive inputs ───────────────────────────────

    @step
    async def receive_inputs(
        self,
        ctx: Context,
        ev: StartEvent,
    ) -> InputsReceivedEvent:
        data = ev.to_dict()
        workflow_run_id: UUID = data["workflow_run_id"]
        goal: str = data["goal"]
        plan: ArchitecturePlan = data["architecture_plan"]
        report: ResearchReport = data["research_report"]
        graph: TaskGraph = data["task_graph"]
        revision_number: int = data.get("revision_number") or 0
        await ctx.store.set("revision_number", revision_number)
        await ctx.store.set("previous_requested_changes", data.get("previous_requested_changes") or [])
        if revision_number:
            logger.info("[Guardian] Guardian reviewing revision=%d | run=%s", revision_number, workflow_run_id)

        logger.info(
            "[Guardian] receive_inputs | run=%s | tasks=%d",
            workflow_run_id, len(graph.tasks),
        )

        return InputsReceivedEvent(
            workflow_run_id=workflow_run_id,
            goal=goal,
            architecture_plan=plan,
            research_report=report,
            task_graph=graph,
        )

    # ── Step 2: Analyze inputs ───────────────────────────────

    @step
    async def analyze_inputs(
        self,
        ctx: Context,
        ev: InputsReceivedEvent,
    ) -> InputsAnalyzedEvent:
        start = time.monotonic()

        prompt = PromptTemplate(GUARDIAN_ANALYSIS_PROMPT)
        analysis_text = await self.llm.complete(
            prompt.format(
                architecture_summary=ev.architecture_plan.summary,
                research_summary=ev.research_report.summary,
                task_graph_summary=format_tasks(ev.task_graph),
            )
        )

        await ctx.store.set("guardian_analysis", analysis_text)

        duration = time.monotonic() - start
        logger.info(
            "[Guardian] analyze_inputs | run=%s | duration=%.2fs",
            ev.workflow_run_id, duration,
        )

        return InputsAnalyzedEvent(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            architecture_plan=ev.architecture_plan,
            research_report=ev.research_report,
            task_graph=ev.task_graph,
        )

    # ── Step 3: Generate review ──────────────────────────────

    @step
    async def generate_review(
        self,
        ctx: Context,
        ev: InputsAnalyzedEvent,
    ) -> ReviewGeneratedEvent:
        revision_number = await ctx.store.get("revision_number", default=0)
        previous = await ctx.store.get("previous_requested_changes", default=[])
        revision_context = ""
        if revision_number:
            revision_context = GUARDIAN_REREVIEW_CONTEXT.format(
                revision_number=revision_number,
                previous_requested_changes="\n".join(f"- {c}" for c in previous) or "- (none recorded)",
            )

        try:
            llm_report = await with_retry(
                llm=self.llm,
                output_cls=LLMValidationReport,
                base_prompt=GUARDIAN_REVIEW_PROMPT,
                max_retries=MAX_RETRIES,
                agent_name="Guardian",
                run_id=str(ev.workflow_run_id),
                architecture_summary=ev.architecture_plan.summary,
                research_summary=ev.research_report.summary,
                task_graph_summary=format_tasks(ev.task_graph),
                revision_context=revision_context,
            )

            return ReviewGeneratedEvent(
                workflow_run_id=ev.workflow_run_id,
                goal=ev.goal,
                llm_report=llm_report,
            )
        except Exception as e:
            raise ReviewGenerationError(str(e)) from e

    # ── Step 4: Validate review ──────────────────────────────

    @step
    async def validate_review(
        self,
        ctx: Context,
        ev: ReviewGeneratedEvent,
    ) -> StopEvent:
        llm_report = ev.llm_report
        errors: list[str] = []

        if err := validate_non_empty(llm_report.summary, "Summary"):
            errors.append(err)
            
        if llm_report.overall_verdict not in ["approved", "needs_revision", "rejected"]:
            errors.append(f"Invalid overall verdict: {llm_report.overall_verdict}")

        if errors:
            raise ReviewValidationError(f"Review validation failed: {'; '.join(errors)}")

        report = ValidationReport(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            summary=llm_report.summary,
            overall_verdict=llm_report.overall_verdict,
            architecture_review=llm_report.architecture_review,
            dependency_review=llm_report.dependency_review,
            security_review=llm_report.security_review,
            performance_review=llm_report.performance_review,
            maintainability_review=llm_report.maintainability_review,
            recommendations=llm_report.recommendations,
        )

        logger.info(
            "[Guardian] validate_review | run=%s | verdict=%s | PASSED",
            report.workflow_run_id, report.overall_verdict,
        )

        return StopEvent(result=report)
