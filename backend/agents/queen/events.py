from uuid import UUID

from llama_index.core.workflow import Event

from agents.queen.schemas import GoalAnalysis, LLMStrategy


class GoalReceivedEvent(Event):
    """Emitted after receive_goal validates and accepts the input."""
    workflow_run_id: UUID
    goal: str
    memory_context: str = ""


class GoalAnalyzedEvent(Event):
    """Emitted after analyze_goal produces structured analysis."""
    workflow_run_id: UUID
    goal: str
    analysis: GoalAnalysis
    memory_context: str = ""


class StrategyGeneratedEvent(Event):
    """Emitted after generate_strategy produces structured output."""
    workflow_run_id: UUID
    goal: str
    llm_strategy: LLMStrategy
