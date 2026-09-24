from uuid import UUID

from app.core.config import settings
from agents.llm.factory import get_llm
from agents.guardian.schemas import ValidationReport
from agents.guardian.workflow import GuardianWorkflow
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import ResearchReport
from agents.builder.schemas import TaskGraph


class GuardianService:
    def __init__(self):
        self.workflow = GuardianWorkflow(
            llm=get_llm(),
            timeout=settings.AGENT_TIMEOUT_S,
        )

    async def generate_review(
        self,
        run_id: UUID,
        goal: str,
        architecture_plan: ArchitecturePlan,
        research_report: ResearchReport,
        task_graph: TaskGraph,
        revision_number: int = 0,
        previous_requested_changes: list[str] | None = None,
    ) -> ValidationReport:
        """Review `task_graph`. For revision_number > 0 this is a re-review of that revision's output."""
        return await self.workflow.run(
            workflow_run_id=run_id,
            goal=goal,
            architecture_plan=architecture_plan,
            research_report=research_report,
            task_graph=task_graph,
            revision_number=revision_number,
            previous_requested_changes=previous_requested_changes or [],
        )
