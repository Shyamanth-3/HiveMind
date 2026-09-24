from uuid import UUID

from pydantic import BaseModel


class AgentOutput(BaseModel):
    """Base output contract for all HiveMind agents."""
    workflow_run_id: UUID
    goal: str
