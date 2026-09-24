from typing import Literal

from pydantic import BaseModel, Field

from agents.base.schemas import AgentOutput


class ArchitectureReview(BaseModel):
    is_sound: bool = Field(..., description="Whether the architecture is sound and meets requirements")
    feedback: str = Field(..., description="Detailed feedback on the architecture")


class DependencyReview(BaseModel):
    has_cycles: bool = Field(..., description="Whether there are circular dependencies")
    feedback: str = Field(..., description="Detailed feedback on the dependencies")


class SecurityReview(BaseModel):
    is_secure: bool = Field(..., description="Whether security considerations are adequately addressed")
    feedback: str = Field(..., description="Detailed feedback on security")


class PerformanceReview(BaseModel):
    is_performant: bool = Field(..., description="Whether performance constraints are addressed")
    feedback: str = Field(..., description="Detailed feedback on performance")


class MaintainabilityReview(BaseModel):
    is_maintainable: bool = Field(..., description="Whether the system will be maintainable")
    feedback: str = Field(..., description="Detailed feedback on maintainability")


class LLMValidationReport(BaseModel):
    """The structured output strictly required from the LLM."""
    summary: str
    overall_verdict: Literal["approved", "needs_revision", "rejected"] = Field(
        ..., description="'approved', 'needs_revision', or 'rejected'")
    architecture_review: ArchitectureReview
    dependency_review: DependencyReview
    security_review: SecurityReview
    performance_review: PerformanceReview
    maintainability_review: MaintainabilityReview
    recommendations: list[str]


class ValidationReport(AgentOutput):
    """The final ValidationReport produced by the Guardian workflow."""
    summary: str
    overall_verdict: Literal["approved", "needs_revision", "rejected"]
    architecture_review: ArchitectureReview
    dependency_review: DependencyReview
    security_review: SecurityReview
    performance_review: PerformanceReview
    maintainability_review: MaintainabilityReview
    recommendations: list[str]
