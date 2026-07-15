"""
Kafka implementation of the EventBus using confluent-kafka.
"""

import logging

from confluent_kafka import Producer, Message, KafkaError

from .event_bus import EventBus
from .schemas import KafkaEvent


logger = logging.getLogger(__name__)


class KafkaEventBus(EventBus):
    """
    Concrete EventBus implementation that publishes events to Apache Kafka.
    """

    def __init__(self, bootstrap_servers: str, topic: str) -> None:
        """
        Initialize the Kafka producer.
        
        Args:
            bootstrap_servers: Comma-separated list of Kafka broker addresses.
            topic: The default Kafka topic to publish events to.
        """
        self.topic = topic
        
        config = {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "hivemind-api",
            # Enable idempotence to ensure strictly exactly-once delivery
            "enable.idempotence": True,
            # Linger slightly to allow batching for better throughput
            "linger.ms": 5,
        }
        
        logger.info(f"Initializing KafkaEventBus for topic '{self.topic}' at {bootstrap_servers}")
        self.producer = Producer(config)

    def _delivery_callback(self, err: KafkaError | None, msg: Message) -> None:
        """
        Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush().
        """
        if err is not None:
            logger.error(f"Failed to deliver message: {err}")
        else:
            # We log at debug level for successful deliveries to avoid flooding logs
            logger.debug(
                f"Message delivered to topic {msg.topic()} "
                f"partition [{msg.partition()}] offset {msg.offset()}"
            )

    def publish(self, event: KafkaEvent) -> None:
        """
        Publish an event to Kafka.
        
        Uses the event's `run_id` as the message key to ensure causal ordering
        within a single workflow execution (all events for a run go to the same partition).
        Falls back to `event_type` if `run_id` is missing.
        """
        try:
            value = event.to_json_bytes()
            # Use run_id as key for partition affinity. Fallback to event_type.
            key = (event.run_id or event.event_type).encode("utf-8")
            
            # Asynchronously produce the message
            self.producer.produce(
                topic=self.topic,
                key=key,
                value=value,
                callback=self._delivery_callback
            )
            
            # Serve delivery callback queue.
            # poll(0) is non-blocking and will just trigger callbacks for previously
            # delivered (or failed) messages.
            self.producer.poll(0)
            
        except Exception as e:
            logger.error(f"Error publishing event {event.event_type}: {e}")
            # Re-raise so the caller can decide how to handle the failure
            raise

    def close(self) -> None:
        """
        Block until all pending messages are delivered or timeout occurs.
        """
        logger.info("Flushing Kafka producer before shutdown...")
        # Block up to 5 seconds waiting for pending messages to be delivered
        unflushed = self.producer.flush(5.0)
        if unflushed > 0:
            logger.warning(f"Failed to flush {unflushed} messages on shutdown")
        else:
            logger.info("Kafka producer flushed successfully")
