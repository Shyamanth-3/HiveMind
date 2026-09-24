from agents.base.exceptions import GenerationError, ValidationError


class GuardianWorkflowError(Exception):
    """Base exception for Guardian workflow failures."""


class ReviewGenerationError(GenerationError):
    """Raised when the LLM fails to produce a valid validation report."""


class ReviewValidationError(ValidationError):
    """Raised when the generated validation report fails validation."""
