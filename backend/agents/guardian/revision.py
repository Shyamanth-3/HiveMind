"""
Revision request: the strict payload of the `revision.requested` event.

Built deterministically from Guardian's validated ValidationReport (never from free text): the
LLM decides the verdict; whether a revision is allowed (MAX_REVISIONS) and what identity it gets is
decided by code.
"""

from uuid import NAMESPACE_OID, uuid5

from pydantic import BaseModel, Field, model_validator

from agents.guardian.schemas import ValidationReport

# (report section, label, attribute that is "bad" when it has this value)
_SECTIONS = [
    ("architecture_review", "architecture", "is_sound", False),
    ("dependency_review", "dependencies", "has_cycles", True),
    ("security_review", "security", "is_secure", False),
    ("performance_review", "performance", "is_performant", False),
    ("maintainability_review", "maintainability", "is_maintainable", False),
]


def revision_id_for(run_id: str, source_review_event_id: str, revision_number: int) -> str:
    """Stable identity of run + source review + revision number: a redelivered review gives the same id."""
    return str(uuid5(NAMESPACE_OID, f"{run_id}:{source_review_event_id}:{revision_number}"))


class RevisionRequest(BaseModel):
    run_id: str
    revision_id: str
    revision_number: int = Field(ge=1, description="1 for the first revision.")
    max_revisions: int = Field(ge=1)
    source_review_event_id: str = Field(description="The review.completed event that asked for this revision.")
    reason: str = Field(min_length=1, description="Guardian's overall summary of why the plan needs revision.")
    feedback: list[str] = Field(min_length=1, description="What Guardian found wrong, per review area.")
    requested_changes: list[str] = Field(min_length=1, description="What must change.")

    @model_validator(mode="after")
    def _within_limit_and_identity(self):
        if self.revision_number > self.max_revisions:
            raise ValueError(f"revision {self.revision_number} exceeds MAX_REVISIONS={self.max_revisions}")
        expected = revision_id_for(self.run_id, self.source_review_event_id, self.revision_number)
        if self.revision_id != expected:
            raise ValueError("revision_id does not match run + source review + revision number")
        return self


def guardian_feedback(report: ValidationReport) -> list[str]:
    """Per-area feedback for the areas Guardian flagged; every area's feedback if none was flagged."""
    flagged, everything = [], []
    for attr, label, flag, bad_value in _SECTIONS:
        section = getattr(report, attr)
        line = f"{label}: {section.feedback.strip()}"
        everything.append(line)
        if getattr(section, flag) == bad_value:
            flagged.append(line)
    return flagged or everything


def build_revision_request(
    report: ValidationReport,
    run_id: str,
    source_review_event_id: str,
    revision_number: int,
    max_revisions: int,
) -> RevisionRequest:
    feedback = guardian_feedback(report)
    changes = [c.strip() for c in report.recommendations if c.strip()] or [report.summary.strip()]
    return RevisionRequest(
        run_id=run_id,
        revision_id=revision_id_for(run_id, source_review_event_id, revision_number),
        revision_number=revision_number,
        max_revisions=max_revisions,
        source_review_event_id=source_review_event_id,
        reason=report.summary.strip(),
        feedback=feedback,
        requested_changes=changes,
    )
