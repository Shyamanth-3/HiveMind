from uuid import UUID
from llama_index.core.workflow import Event
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import LLMResearchReport


class PlanReceivedEvent(Event):
    """Emitted after the Scout receives the architecture plan."""
    workflow_run_id: UUID
    goal: str
    architecture_plan: ArchitecturePlan


class PlanAnalyzedEvent(Event):
    """Emitted after the Scout analyzes the architecture plan."""
    workflow_run_id: UUID
    goal: str
    architecture_plan: ArchitecturePlan


class ResearchGeneratedEvent(Event):
    """Emitted after the Scout generates the research report."""
    workflow_run_id: UUID
    goal: str
    llm_report: LLMResearchReport
