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
from agents.architect.events import (
    StrategyReceivedEvent,
    StrategyAnalyzedEvent,
    PlanGeneratedEvent,
)
from agents.architect.exceptions import (
    ArchitectureGenerationError,
    ArchitectureValidationError,
)
from agents.architect.prompts import ARCHITECT_ANALYSIS_PROMPT, ARCHITECT_PLAN_PROMPT
from agents.architect.schemas import LLMArchitecturePlan, ArchitecturePlan
from agents.queen.schemas import Strategy

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
MIN_COMPONENTS = 2
MAX_COMPONENTS = 15


class ArchitectWorkflow(Workflow):

    def __init__(self, llm: LLMClient, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm

    # ── Step 1: Receive strategy ─────────────────────────────

    @step
    async def receive_strategy(
        self,
        ctx: Context,
        ev: StartEvent,
    ) -> StrategyReceivedEvent:
        data = ev.to_dict()
        workflow_run_id: UUID = data["workflow_run_id"]
        goal: str = data["goal"]
        strategy: Strategy = data["strategy"]

        logger.info(
            "[Architect] receive_strategy | run=%s | phases=%d",
            workflow_run_id, len(strategy.phases),
        )

        return StrategyReceivedEvent(
            workflow_run_id=workflow_run_id,
            goal=goal,
            strategy=strategy,
        )

    # ── Step 2: Analyze strategy ─────────────────────────────

    @step
    async def analyze_strategy(
        self,
        ctx: Context,
        ev: StrategyReceivedEvent,
    ) -> StrategyAnalyzedEvent:
        start = time.monotonic()
        strategy = ev.strategy

        # Simple text analysis since Architect needs to build on the strategy
        strategy_phases = "\n".join(
            [f"- [{p.id}] {p.title}: {p.description}" for p in strategy.phases]
        )

        prompt = PromptTemplate(ARCHITECT_ANALYSIS_PROMPT)
        analysis_text = await self.llm.complete(
            prompt.format(
                strategy_summary=strategy.summary,
                strategy_phases=strategy_phases,
            )
        )

        await ctx.store.set("architect_analysis", analysis_text)

        duration = time.monotonic() - start
        logger.info(
            "[Architect] analyze_strategy | run=%s | duration=%.2fs",
            ev.workflow_run_id, duration,
        )

        return StrategyAnalyzedEvent(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            strategy=ev.strategy,
        )

    # ── Step 3: Generate architecture plan ───────────────────

    @step
    async def generate_plan(
        self,
        ctx: Context,
        ev: StrategyAnalyzedEvent,
    ) -> PlanGeneratedEvent:
        strategy = ev.strategy
        
        strategy_phases = "\n".join(
            [f"- [{p.id}] {p.title}: {p.description}" for p in strategy.phases]
        )

        try:
            llm_plan = await with_retry(
                llm=self.llm,
                output_cls=LLMArchitecturePlan,
                base_prompt=ARCHITECT_PLAN_PROMPT,
                max_retries=MAX_RETRIES,
                agent_name="Architect",
                run_id=str(ev.workflow_run_id),
                strategy_summary=strategy.summary,
                strategy_phases=strategy_phases,
            )
            
            return PlanGeneratedEvent(
                workflow_run_id=ev.workflow_run_id,
                goal=ev.goal,
                llm_plan=llm_plan,
            )
        except Exception as e:
            raise ArchitectureGenerationError(str(e)) from e

    # ── Step 4: Validate plan ────────────────────────────────

    @step
    async def validate_plan(
        self,
        ctx: Context,
        ev: PlanGeneratedEvent,
    ) -> StopEvent:
        llm_plan = ev.llm_plan
        errors: list[str] = []

        if err := validate_non_empty(llm_plan.summary, "Summary"):
            errors.append(err)
            
        if err := validate_min_max_count(llm_plan.components, MIN_COMPONENTS, MAX_COMPONENTS, "components"):
            errors.append(err)

        if err := validate_min_max_count(llm_plan.milestones, 1, 10, "milestones"):
            errors.append(err)

        # Validate unique component IDs
        component_ids = [c.id for c in llm_plan.components]
        if len(component_ids) != len(set(component_ids)):
            errors.append("Component IDs must be unique.")

        # Validate dependencies reference valid components
        for dep in llm_plan.dependencies:
            if dep.source_id not in component_ids:
                errors.append(f"Dependency source {dep.source_id} not in components.")
            if dep.target_id not in component_ids:
                errors.append(f"Dependency target {dep.target_id} not in components.")
                
        # Validate milestones reference valid components
        for ms in llm_plan.milestones:
            for c_id in ms.components:
                if c_id not in component_ids:
                    errors.append(f"Milestone {ms.id} references invalid component {c_id}.")

        if errors:
            raise ArchitectureValidationError(f"Architecture validation failed: {'; '.join(errors)}")

        plan = ArchitecturePlan(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            summary=llm_plan.summary,
            components=llm_plan.components,
            dependencies=llm_plan.dependencies,
            execution_order=llm_plan.execution_order,
            milestones=llm_plan.milestones,
            risk_assessment=llm_plan.risk_assessment,
        )

        logger.info(
            "[Architect] validate_plan | run=%s | components=%d | PASSED",
            plan.workflow_run_id, len(plan.components),
        )

        return StopEvent(result=plan)
