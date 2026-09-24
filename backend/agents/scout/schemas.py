from pydantic import BaseModel, Field

from agents.base.schemas import AgentOutput


class ResearchFinding(BaseModel):
    topic: str = Field(..., description="Topic of the research finding")
    finding: str = Field(..., description="Detailed description of what was discovered")
    source_type: str = Field(..., description="E.g., web search, documentation, vector DB")
    relevance: str = Field(..., description="How this finding impacts the architecture")


class LibraryRecommendation(BaseModel):
    name: str = Field(..., description="Name of the library or framework")
    purpose: str = Field(..., description="What the library will be used for")
    rationale: str = Field(..., description="Why this specific library is recommended over alternatives")


class SecurityConsideration(BaseModel):
    area: str = Field(..., description="The architectural area affected (e.g., auth, database, api)")
    concern: str = Field(..., description="The specific security concern or vulnerability")
    recommendation: str = Field(..., description="Actionable recommendation to address the concern")
    severity: str = Field(..., description="high, medium, or low")


class LLMResearchReport(BaseModel):
    """The structured output strictly required from the LLM."""
    summary: str
    findings: list[ResearchFinding]
    library_recommendations: list[LibraryRecommendation]
    security_considerations: list[SecurityConsideration]
    performance_considerations: list[str]


class ResearchReport(AgentOutput):
    """The final ResearchReport produced by the Scout workflow."""
    summary: str
    findings: list[ResearchFinding]
    library_recommendations: list[LibraryRecommendation]
    security_considerations: list[SecurityConsideration]
    performance_considerations: list[str]
