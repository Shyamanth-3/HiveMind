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

from app.db.database import SessionLocal
from app.core.config import settings
from app.memory.extraction import MemoryExtraction, sanitize_candidates
from app.memory.formatting import NO_MEMORIES, format_memory_context
from app.memory.schemas import MemoryStoreRequest
from app.memory.service import MemoryService

from agents.base.retry import with_retry
from agents.base.validation import validate_min_max_count, validate_non_empty, validate_sequential_ids
from agents.queen.events import (
    GoalAnalyzedEvent,
    GoalReceivedEvent,
    StrategyGeneratedEvent,
)
from agents.queen.exceptions import (
    StrategyGenerationError,
    StrategyValidationError,
)
from agents.queen.prompts import QUEEN_ANALYSIS_PROMPT, QUEEN_MEMORY_PROMPT, QUEEN_STRATEGY_PROMPT
from agents.queen.schemas import GoalAnalysis, LLMStrategy, Strategy

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
MIN_PHASES = 2
MAX_PHASES = 7


class QueenWorkflow(Workflow):

    def __init__(self, llm: LLMClient, memory_service: MemoryService, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm
        self.memory_service = memory_service

    # ── Step 1: Receive & validate input ─────────────────────

    @step
    async def receive_goal(
        self,
        ctx: Context,
        ev: StartEvent,
    ) -> GoalReceivedEvent:
        data = ev.to_dict()
        workflow_run_id: UUID = data["workflow_run_id"]
        goal: str = data["goal"]

        logger.info(
            "[Queen] receive_goal | run=%s | goal_length=%d",
            workflow_run_id, len(goal),
        )
        
        project_id: str = data["project_id"]
        await ctx.store.set("project_id", project_id)
        await ctx.store.set("source_event_id", data.get("source_event_id"))

        if not self.memory_service.enabled:
            logger.info("[Queen] Memory disabled (EMBEDDING_PROVIDER=none): skipping retrieval")
            memory_context = NO_MEMORIES
        else:
            # Errors propagate: a configured-but-failing memory must fail the run, not pass silently.
            with SessionLocal() as db:
                memories = await self.memory_service.retrieve_memories(
                    db, query=goal, project_id=project_id, run_id=str(workflow_run_id))
            memory_context = format_memory_context(memories)

        return GoalReceivedEvent(
            workflow_run_id=workflow_run_id,
            goal=goal,
            memory_context=memory_context,
        )

    # ── Step 2: Analyze goal via structured LLM call ─────────

    @step
    async def analyze_goal(
        self,
        ctx: Context,
        ev: GoalReceivedEvent,
    ) -> GoalAnalyzedEvent:
        start = time.monotonic()

        analysis = await with_retry(
            llm=self.llm,
            output_cls=GoalAnalysis,
            base_prompt=QUEEN_ANALYSIS_PROMPT,
            max_retries=MAX_RETRIES,
            agent_name="Queen",
            run_id=str(ev.workflow_run_id),
            goal=ev.goal,
        )

        # Store analysis as dynamic workflow state
        await ctx.store.set("goal_analysis", analysis.model_dump())

        duration = time.monotonic() - start
        logger.info(
            "[Queen] analyze_goal | run=%s | complexity=%s | type=%s | est_phases=%d | needs_research=%s | duration=%.2fs",
            ev.workflow_run_id, analysis.complexity, analysis.project_type,
            analysis.estimated_phases, analysis.needs_research, duration,
        )

        return GoalAnalyzedEvent(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            analysis=analysis,
            memory_context=ev.memory_context,
        )

    # ── Step 3: Generate structured strategy ─────────────────

    @step
    async def generate_strategy(
        self,
        ctx: Context,
        ev: GoalAnalyzedEvent,
    ) -> StrategyGeneratedEvent:
        analysis = ev.analysis
        
        try:
            llm_strategy = await with_retry(
                llm=self.llm,
                output_cls=LLMStrategy,
                base_prompt=QUEEN_STRATEGY_PROMPT,
                max_retries=MAX_RETRIES,
                agent_name="Queen",
                run_id=str(ev.workflow_run_id),
                goal=ev.goal,
                complexity=analysis.complexity,
                project_type=analysis.project_type,
                estimated_phases=analysis.estimated_phases,
                memory_context=ev.memory_context,
            )
            
            return StrategyGeneratedEvent(
                workflow_run_id=ev.workflow_run_id,
                goal=ev.goal,
                llm_strategy=llm_strategy,
            )
        except Exception as e:
            raise StrategyGenerationError(str(e)) from e

    # ── Step 4: Validate strategy ────────────────────────────

    @step
    async def validate_strategy(
        self,
        ctx: Context,
        ev: StrategyGeneratedEvent,
    ) -> StopEvent:
        llm_strategy = ev.llm_strategy
        errors: list[str] = []

        # Use base validation helpers
        if err := validate_non_empty(llm_strategy.summary, "Summary"):
            errors.append(err)
            
        if err := validate_min_max_count(llm_strategy.phases, MIN_PHASES, MAX_PHASES, "phases"):
            errors.append(err)

        # Empty titles
        empty_titles = [p.id for p in llm_strategy.phases if not p.title.strip()]
        if empty_titles:
            errors.append(f"Phases with empty titles: {empty_titles}")

        # Sequential IDs
        if err := validate_sequential_ids(llm_strategy.phases):
            errors.append(f"Phase {err}")

        if errors:
            raise StrategyValidationError(f"Strategy validation failed: {'; '.join(errors)}")

        strategy = Strategy(
            workflow_run_id=ev.workflow_run_id,
            goal=ev.goal,
            summary=llm_strategy.summary,
            phases=llm_strategy.phases,
        )

        logger.info(
            "[Queen] validate_strategy | run=%s | phases=%d | PASSED",
            strategy.workflow_run_id, len(strategy.phases),
        )
        
        await self._extract_and_store_memories(ctx, ev.workflow_run_id, ev.goal, strategy)

        return StopEvent(result=strategy)

    # ── Memory extraction (durable facts only, never whole outputs) ──

    async def _extract_and_store_memories(self, ctx: Context, run_id: UUID, goal: str, strategy: Strategy) -> None:
        if not self.memory_service.enabled:
            logger.info("[Queen] Memory disabled (EMBEDDING_PROVIDER=none): nothing stored")
            return

        extraction = await with_retry(
            llm=self.llm,
            output_cls=MemoryExtraction,
            base_prompt=QUEEN_MEMORY_PROMPT,
            max_retries=MAX_RETRIES,
            agent_name="Queen",
            run_id=str(run_id),
            max_memories=settings.MEMORY_MAX_PER_RUN,
            goal=goal,
            strategy_summary=strategy.summary,
        )
        candidates = sanitize_candidates(extraction, settings.MEMORY_MAX_PER_RUN)
        project_id = await ctx.store.get("project_id")
        source_event_id = await ctx.store.get("source_event_id", default=None)

        created = 0
        for mtype, content, importance in candidates:
            with SessionLocal() as db:
                result = await self.memory_service.store_memory(db, MemoryStoreRequest(
                    content=content, agent="queen", project_id=project_id, memory_type=mtype,
                    importance=importance, run_id=str(run_id), source_event_id=source_event_id,
                ))
            created += result.created
        logger.info("[Queen] Memory extraction done | run=%s | proposed=%d | kept=%d | new=%d",
                    run_id, len(extraction.memories), len(candidates), created)
