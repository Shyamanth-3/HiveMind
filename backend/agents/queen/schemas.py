from pydantic import BaseModel, Field

from agents.base.schemas import AgentOutput


class GoalAnalysis(BaseModel):
    """Structured analysis of the incoming goal. Produced by analyze_goal step."""
    complexity: str = Field(description="One of: low, medium, high.")
    estimated_phases: int = Field(description="Estimated number of execution phases needed (3-7).")
    project_type: str = Field(description="Category such as: web_app, api, cli, library, infrastructure, data_pipeline, multi_agent_system.")
    needs_research: bool = Field(description="Whether the goal requires external research before planning.")
    reasoning: str = Field(description="Brief explanation of the analysis conclusions.")


class StrategyPhase(BaseModel):
    """A single execution phase within a strategy."""
    id: int = Field(description="Sequential phase identifier starting from 1.")
    title: str = Field(description="Short, descriptive title for this phase.")
    description: str = Field(description="Clear explanation of what this phase accomplishes and its key deliverables.")


class LLMStrategy(BaseModel):
    """Schema for structured LLM output. The LLM fills this directly."""
    summary: str = Field(description="A concise 2-3 sentence overview of the entire strategy.")
    phases: list[StrategyPhase] = Field(description="Ordered list of execution phases.")


class Strategy(AgentOutput):
    """Complete strategy result returned by the Queen workflow."""
    summary: str
    phases: list[StrategyPhase]