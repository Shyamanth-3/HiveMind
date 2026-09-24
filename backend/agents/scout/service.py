from uuid import UUID

from app.core.config import settings
from agents.llm.factory import get_llm
from agents.scout.schemas import ResearchReport
from agents.scout.workflow import ScoutWorkflow
from agents.architect.schemas import ArchitecturePlan


class ScoutService:
    def __init__(self):
        self.workflow = ScoutWorkflow(
            llm=get_llm(),
            timeout=settings.AGENT_TIMEOUT_S,
        )

    # ── External Interfaces placeholder ────────────────────────
    # As per implementation plan, we only implement the workflow
    # today. In the future, this service will connect to:
    # 
    # def search_web(query)
    # def search_github(repo)
    # def search_docs(topic)
    # def search_vector_db(query)
    # ─────────────────────────────────────────────────────────

    async def generate_research(
        self,
        run_id: UUID,
        goal: str,
        architecture_plan: ArchitecturePlan,
    ) -> ResearchReport:
        return await self.workflow.run(
            workflow_run_id=run_id,
            goal=goal,
            architecture_plan=architecture_plan,
        )
