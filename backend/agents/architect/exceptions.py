from agents.base.exceptions import GenerationError, ValidationError


class ArchitectWorkflowError(Exception):
    """Base exception for Architect workflow failures."""


class ArchitectureGenerationError(GenerationError):
    """Raised when the LLM fails to produce a valid architecture plan."""


class ArchitectureValidationError(ValidationError):
    """Raised when the generated architecture plan fails validation."""
