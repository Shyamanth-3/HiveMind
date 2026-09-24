from agents.base.exceptions import GenerationError, ValidationError


class QueenWorkflowError(Exception):
    """Base exception for Queen workflow failures."""


class StrategyGenerationError(GenerationError):
    """Raised when the LLM fails to produce a valid strategy."""


class StrategyValidationError(ValidationError):
    """Raised when the generated strategy fails validation."""
