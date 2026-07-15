"""
Kafka consumer for the Scheduler.
"""

import json
import logging
from typing import Callable, Dict

from confluent_kafka import Consumer, KafkaError, KafkaException
from pydantic import ValidationError

from app.events.schemas import KafkaEvent
from app.events.event_types import EventTypes

logger = logging.getLogger(__name__)


class SchedulerConsumer:
    """
    Consumes events from Kafka and dispatches them to appropriate handlers.
    The Scheduler is responsible for workflow orchestration (deciding which agent runs next).
    """

    def __init__(self, bootstrap_servers: str, topic: str, group_id: str) -> None:
        self.topic = topic
        self.running = False
        
        config = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
        
        logger.info(f"Initializing SchedulerConsumer for topic '{self.topic}' (group: {group_id})")
        self.consumer = Consumer(config)
        
        # Dispatch table: EventTypes -> Handler Function
        self._handlers: Dict[str, Callable[[KafkaEvent], None]] = {
            EventTypes.RUN_CREATED: self._handle_run_created,
            # Future handlers will be registered here (e.g., STRATEGY_CREATED -> Architect)
        }

    def _handle_run_created(self, event: KafkaEvent) -> None:
        """
        Handler for the run.created event.
        Currently just logs it. In the future, this will dispatch the Queen agent.
        """
        logger.info(
            f"🚀 [SCHEDULER] Processing new run: {event.run_id} "
            f"(Goal: '{event.payload.get('goal', 'Unknown')}')"
        )

    def _dispatch(self, event: KafkaEvent) -> None:
        """Look up the handler by event_type and call it."""
        handler = self._handlers.get(event.event_type)
        if handler:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in handler for {event.event_type}: {e}", exc_info=True)
        else:
            logger.debug(f"No handler registered for event type: {event.event_type}")

    def start(self) -> None:
        """
        Start the consumer polling loop. Blocks until stop() is called.
        """
        self.consumer.subscribe([self.topic])
        self.running = True
        
        logger.info(f"SchedulerConsumer started, listening on {self.topic}...")
        
        try:
            while self.running:
                # Poll with 1.0s timeout to allow clean shutdown checks
                msg = self.consumer.poll(1.0)
                
                if msg is None:
                    continue
                
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition event (not a real error)
                        continue
                    else:
                        logger.error(f"Consumer error: {msg.error()}")
                        continue
                
                # Process valid message
                try:
                    value = msg.value()
                    if value:
                        payload_dict = json.loads(value.decode("utf-8"))
                        event = KafkaEvent.model_validate(payload_dict)
                        self._dispatch(event)
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode message JSON: {e}")
                except ValidationError as e:
                    logger.error(f"Message validation failed: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error processing message: {e}", exc_info=True)
                    
        except KeyboardInterrupt:
            logger.info("SchedulerConsumer interrupted by user")
        finally:
            logger.info("Closing SchedulerConsumer...")
            self.consumer.close()

    def stop(self) -> None:
        """
        Signal the polling loop to stop gracefully.
        """
        self.running = False
