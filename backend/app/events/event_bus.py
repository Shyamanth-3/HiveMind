"""
Abstract interface for the EventBus.
"""

from abc import ABC, abstractmethod

from .schemas import KafkaEvent


class EventBus(ABC):
    """
    Abstract interface for publishing events to the event stream.
    
    This abstraction ensures the core business logic (like services) doesn't depend
    on the specific messaging infrastructure (Kafka, Redis, In-Memory, etc.).
    """

    @abstractmethod
    def publish(self, event: KafkaEvent) -> None:
        """
        Publish an event to the event stream.
        Returns only after the event is durably delivered; raises if delivery fails.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Cleanly shut down the event bus, ensuring any pending messages are delivered.
        """
        pass
