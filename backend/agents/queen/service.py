from uuid import UUID

from app.core.config import settings
from agents.llm.factory import get_llm
from agents.queen.schemas import Strategy
from agents.queen.workflow import QueenWorkflow
from app.memory.service import MemoryService


class QueenService:
    def __init__(self):
        self.workflow = QueenWorkflow(
            llm=get_llm(),
            memory_service=MemoryService(),
            timeout=settings.AGENT_TIMEOUT_S,
        )

    async def generate_strategy(
        self,
        run_id: UUID,
        goal: str,
        project_id: str,
        source_event_id: str | None = None,
    ) -> Strategy:
        return await self.workflow.run(
            workflow_run_id=run_id,
            goal=goal,
            project_id=project_id,
            source_event_id=source_event_id,
        )