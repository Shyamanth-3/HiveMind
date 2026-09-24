from uuid import UUID
from llama_index.core.workflow import Event
from agents.queen.schemas import Strategy
from agents.architect.schemas import LLMArchitecturePlan


class StrategyReceivedEvent(Event):
    """Emitted after the Architect receives the strategy."""
    workflow_run_id: UUID
    goal: str
    strategy: Strategy


class StrategyAnalyzedEvent(Event):
    """Emitted after the Architect analyzes the strategy."""
    workflow_run_id: UUID
    goal: str
    strategy: Strategy


class PlanGeneratedEvent(Event):
    """Emitted after the Architect generates the architecture plan."""
    workflow_run_id: UUID
    goal: str
    llm_plan: LLMArchitecturePlan
