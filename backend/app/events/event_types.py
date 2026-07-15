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
    TASKS_GENERATED = "tasks.generated"
    RESEARCH_COMPLETED = "research.completed"
    BUILD_COMPLETED = "build.completed"
    REVIEW_COMPLETED = "review.completed"
