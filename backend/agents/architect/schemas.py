from pydantic import BaseModel, Field

from agents.base.schemas import AgentOutput


class Component(BaseModel):
    id: str = Field(..., description="Unique identifier for the component")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="What this component does")
    layer: str = Field(..., description="Architectural layer (e.g., frontend, backend, database, infrastructure)")


class Dependency(BaseModel):
    source_id: str = Field(..., description="ID of the component that depends on another")
    target_id: str = Field(..., description="ID of the component being depended on")
    relationship: str = Field(..., description="Description of the dependency")


class Milestone(BaseModel):
    id: str = Field(..., description="Unique identifier for the milestone")
    title: str = Field(..., description="Milestone title")
    description: str = Field(..., description="Milestone description")
    components: list[str] = Field(..., description="List of component IDs included in this milestone")


class RiskAssessment(BaseModel):
    area: str = Field(..., description="Risk area (e.g., security, performance, integration)")
    risk: str = Field(..., description="Description of the risk")
    severity: str = Field(..., description="high, medium, or low")
    mitigation: str = Field(..., description="How to mitigate the risk")


class LLMArchitecturePlan(BaseModel):
    """The structured output strictly required from the LLM."""
    summary: str
    components: list[Component]
    dependencies: list[Dependency]
    execution_order: list[str]
    milestones: list[Milestone]
    risk_assessment: list[RiskAssessment]


class ArchitecturePlan(AgentOutput):
    """The final ArchitecturePlan produced by the Architect workflow."""
    summary: str
    components: list[Component]
    dependencies: list[Dependency]
    execution_order: list[str]
    milestones: list[Milestone]
    risk_assessment: list[RiskAssessment]
