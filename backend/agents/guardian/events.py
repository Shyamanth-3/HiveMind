from uuid import UUID
from llama_index.core.workflow import Event
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import ResearchReport
from agents.builder.schemas import TaskGraph
from agents.guardian.schemas import LLMValidationReport


class InputsReceivedEvent(Event):
    """Emitted after the Guardian receives all inputs."""
    workflow_run_id: UUID
    goal: str
    architecture_plan: ArchitecturePlan
    research_report: ResearchReport
    task_graph: TaskGraph


class InputsAnalyzedEvent(Event):
    """Emitted after the Guardian analyzes the inputs."""
    workflow_run_id: UUID
    goal: str
    architecture_plan: ArchitecturePlan
    research_report: ResearchReport
    task_graph: TaskGraph


class ReviewGeneratedEvent(Event):
    """Emitted after the Guardian generates the validation report."""
    workflow_run_id: UUID
    goal: str
    llm_report: LLMValidationReport
