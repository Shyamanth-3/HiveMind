from agents.base.exceptions import GenerationError, ValidationError


class ScoutWorkflowError(Exception):
    """Base exception for Scout workflow failures."""


class ResearchGenerationError(GenerationError):
    """Raised when the LLM fails to produce a valid research report."""


class ResearchValidationError(ValidationError):
    """Raised when the generated research report fails validation."""
