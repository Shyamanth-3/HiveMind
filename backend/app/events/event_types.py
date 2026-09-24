"""
Centralized event type constants.
"""

from enum import Enum


class EventTypes(str, Enum):
    """
    All valid Kafka event types for the system.
    Using an Enum ensures we don't scatter magic strings throughout the codebase.
    """
    RUN_CREATED = "run.created"
    STRATEGY_CREATED = "strategy.created"
    ARCHITECTURE_CREATED = "architecture.created"
    RESEARCH_COMPLETED = "research.completed"
    TASKS_GENERATED = "tasks.generated"
    REVIEW_COMPLETED = "review.completed"
    REVISION_REQUESTED = "revision.requested"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
