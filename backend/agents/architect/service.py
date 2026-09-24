from uuid import UUID

from app.core.config import settings
from agents.llm.factory import get_llm
from agents.architect.schemas import ArchitecturePlan
from agents.architect.workflow import ArchitectWorkflow
from agents.queen.schemas import Strategy


class ArchitectService:
    def __init__(self):
        self.workflow = ArchitectWorkflow(
            llm=get_llm(),
            timeout=settings.AGENT_TIMEOUT_S,
        )

    async def generate_plan(
        self,
        run_id: UUID,
        goal: str,
        strategy: Strategy,
    ) -> ArchitecturePlan:
        return await self.workflow.run(
            workflow_run_id=run_id,
            goal=goal,
            strategy=strategy,
        )
