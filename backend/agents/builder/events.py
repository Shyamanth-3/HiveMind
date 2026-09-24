from uuid import UUID
from llama_index.core.workflow import Event
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import ResearchReport
from agents.builder.schemas import LLMTaskGraph


class ResearchReceivedEvent(Event):
    """Emitted after the Builder receives the architecture plan and research report."""
    workflow_run_id: UUID
    goal: str
    architecture_plan: ArchitecturePlan
    research_report: ResearchReport


class InputsAnalyzedEvent(Event):
    """Emitted after the Builder analyzes the inputs."""
    workflow_run_id: UUID
    goal: str
    architecture_plan: ArchitecturePlan
    research_report: ResearchReport


class TaskGraphGeneratedEvent(Event):
    """Emitted after the Builder generates the task graph."""
    workflow_run_id: UUID
    goal: str
    llm_task_graph: LLMTaskGraph
