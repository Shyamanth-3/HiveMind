from agents.base.exceptions import GenerationError, ValidationError


class BuilderWorkflowError(Exception):
    """Base exception for Builder workflow failures."""


class TaskGraphGenerationError(GenerationError):
    """Raised when the LLM fails to produce a valid task graph."""


class TaskGraphValidationError(ValidationError):
    """Raised when the generated task graph fails validation."""
