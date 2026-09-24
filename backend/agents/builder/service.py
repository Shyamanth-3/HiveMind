from uuid import UUID

from app.core.config import settings
from agents.llm.factory import get_llm
from agents.builder.schemas import TaskGraph
from agents.builder.workflow import BuilderWorkflow
from agents.guardian.revision import RevisionRequest
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import ResearchReport


class BuilderService:
    def __init__(self):
        self.workflow = BuilderWorkflow(
            llm=get_llm(),
            timeout=settings.AGENT_TIMEOUT_S,
        )

    async def generate_task_graph(
        self,
        run_id: UUID,
        goal: str,
        architecture_plan: ArchitecturePlan,
        research_report: ResearchReport,
    ) -> TaskGraph:
        return await self.workflow.run(
            workflow_run_id=run_id,
            goal=goal,
            architecture_plan=architecture_plan,
            research_report=research_report,
        )

    async def revise_task_graph(
        self,
        run_id: UUID,
        goal: str,
        architecture_plan: ArchitecturePlan,
        research_report: ResearchReport,
        previous_graph: TaskGraph,
        revision: RevisionRequest,
    ) -> TaskGraph:
        """Revise `previous_graph` according to the Guardian's feedback (same output schema)."""
        return await self.workflow.run(
            workflow_run_id=run_id,
            goal=goal,
            architecture_plan=architecture_plan,
            research_report=research_report,
            previous_graph=previous_graph,
            revision=revision,
        )
