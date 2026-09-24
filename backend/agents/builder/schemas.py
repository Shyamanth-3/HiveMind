from pydantic import BaseModel, Field

from agents.base.schemas import AgentOutput


class TaskNode(BaseModel):
    id: int = Field(..., description="Unique integer ID for the task")
    title: str = Field(..., description="Title of the task")
    description: str = Field(..., description="Detailed explanation of what needs to be built")
    priority: str = Field(..., description="critical, high, medium, or low")
    dependencies: list[int] = Field(..., description="List of task IDs that must be completed before this one")
    estimated_complexity: str = Field(..., description="low, medium, or high")
    required_files: list[str] = Field(..., description="Files that will likely need to be created or modified")
    acceptance_criteria: list[str] = Field(..., description="Criteria that must be met to consider the task complete")
    assigned_agent: str = Field(..., description="The backend role key of the agent to execute this task (e.g., developer_agent)")


class LLMTaskGraph(BaseModel):
    """The structured output strictly required from the LLM."""
    summary: str
    tasks: list[TaskNode]


class TaskGraph(AgentOutput):
    """The final TaskGraph produced by the Builder workflow."""
    summary: str
    tasks: list[TaskNode]
