"""
FastAPI dependency providers.
"""

from fastapi import Request

from app.events.event_bus import EventBus


def get_event_bus(request: Request) -> EventBus:
    """
    Inject the EventBus abstraction from the application state.
    
    This ensures that routers and services only depend on the abstract
    EventBus interface, not the concrete Kafka implementation.
    """
    return request.app.state.event_bus
