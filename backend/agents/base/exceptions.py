"""
Base exceptions for all HiveMind agents.
"""

class AgentWorkflowError(Exception):
    """Base exception for all agent workflow failures."""


class GenerationError(AgentWorkflowError):
    """Raised when the LLM fails to produce a valid output."""


class ValidationError(AgentWorkflowError):
    """Raised when the generated output fails structural or business logic validation."""
