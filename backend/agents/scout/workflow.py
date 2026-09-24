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
from agents.scout.events import (
    PlanReceivedEvent,
    PlanAnalyzedEvent,
    ResearchGeneratedEvent,
)
from agents.scout.exceptions import (
    ResearchGenerationError,
    ResearchValidationError,
)
from agents.scout.prompts import SCOUT_ANALYSIS_PROMPT, SCOUT_RESEARCH_PROMPT
from agents.scout.schemas import LLMResearchReport, ResearchReport
from agents.architect.schemas import ArchitecturePlan

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


class ScoutWorkflow(Workflow):

    def __init__(self, llm: LLMClient, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm

    # ── Step 1: Receive architecture plan ────────────────────

    @step
    async def receive_plan(
        self,
        ctx: Context,
        ev: StartEvent,
    ) -> PlanReceivedEvent:
        data = ev.to_dict()
        workflow_run_id: UUID = data["workflow_run_id"]
        goal: str = data["goal"]
        plan: ArchitecturePlan = data["architecture_plan"]

        logger.info(
            "[Scout] receive_plan | run=%s | components=%d",
            workflow_run_id, len(plan.components),
        )

        return PlanReceivedEvent(
            workflow_run_id=workflow_run_id,
            goal=goal,
            architecture_plan=plan,
        )

    # ── Step 2: Analyze architecture plan ────────────────────

    @step
    async def analyze_plan(
        self,
        ctx: Context,
        ev: PlanReceivedEvent,
    ) -> PlanAnalyzedEvent:
        start = time.monotonic()
        plan = ev.architecture_plan

        plan_components = "\n".join(
            [f"- {c.name} ({c.layer}): {c.description}" for c in plan.components]
        )

        prompt = PromptTemplate(SCOUT_ANALYSIS_PROMPT)
        analysis_text = await self.llm.complete(
            prompt.format(
                architecture_summary=plan.summary,
                architecture_components=plan_components,
            )
        )

        await ctx.store.set("scout_analysis", analysis_text)

        duration = time.monotonic() - start
        logger.info(
            "[Scout] analyze_plan | run=%s | duration=%.2fs",
            ev.workflow_run_id, duration,
        )

        return PlanAnalyzedEvent(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            architecture_plan=ev.architecture_plan,
        )

    # ── Step 3: Generate research report ─────────────────────

    @step
    async def generate_research(
        self,
        ctx: Context,
        ev: PlanAnalyzedEvent,
    ) -> ResearchGeneratedEvent:
        plan = ev.architecture_plan
        
        plan_components = "\n".join(
            [f"- {c.name} ({c.layer}): {c.description}" for c in plan.components]
        )

        try:
            llm_report = await with_retry(
                llm=self.llm,
                output_cls=LLMResearchReport,
                base_prompt=SCOUT_RESEARCH_PROMPT,
                max_retries=MAX_RETRIES,
                agent_name="Scout",
                run_id=str(ev.workflow_run_id),
                architecture_summary=plan.summary,
                architecture_components=plan_components,
            )
            
            return ResearchGeneratedEvent(
                workflow_run_id=ev.workflow_run_id,
                goal=ev.goal,
                llm_report=llm_report,
            )
        except Exception as e:
            raise ResearchGenerationError(str(e)) from e

    # ── Step 4: Validate research report ─────────────────────

    @step
    async def validate_research(
        self,
        ctx: Context,
        ev: ResearchGeneratedEvent,
    ) -> StopEvent:
        llm_report = ev.llm_report
        errors: list[str] = []

        if err := validate_non_empty(llm_report.summary, "Summary"):
            errors.append(err)
            
        if not llm_report.findings and not llm_report.library_recommendations and not llm_report.security_considerations:
            errors.append("Research report must contain at least some findings, recommendations, or security considerations.")

        if errors:
            raise ResearchValidationError(f"Research validation failed: {'; '.join(errors)}")

        report = ResearchReport(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            summary=llm_report.summary,
            findings=llm_report.findings,
            library_recommendations=llm_report.library_recommendations,
            security_considerations=llm_report.security_considerations,
            performance_considerations=llm_report.performance_considerations,
        )

        logger.info(
            "[Scout] validate_research | run=%s | PASSED",
            report.workflow_run_id,
        )

        return StopEvent(result=report)
