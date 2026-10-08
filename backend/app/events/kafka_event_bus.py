"""
Kafka implementation of the EventBus using confluent-kafka.
"""

import logging

from confluent_kafka import Producer, Message, KafkaError

from app.core.kafka_config import kafka_security_config

from .event_bus import EventBus
from .schemas import KafkaEvent


logger = logging.getLogger(__name__)


class EventPublishError(Exception):
    """An event could not be delivered to Kafka."""


class KafkaEventBus(EventBus):
    """
    Concrete EventBus implementation that publishes events to Apache Kafka.
    """

    DELIVERY_TIMEOUT_S = 15.0

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
            # Idempotent producer: retries inside the producer never duplicate/reorder
            "enable.idempotence": True,
            # Linger slightly to allow batching for better throughput
            "linger.ms": 5,
            # Fail delivery (and so publish()) within 10s instead of the 5 min default
            "message.timeout.ms": 10000,
        }
        
        config.update(kafka_security_config())
        logger.info(f"Initializing KafkaEventBus for topic '{self.topic}' at {bootstrap_servers}")
        self.producer = Producer(config)

    def publish(self, event: KafkaEvent) -> None:
        """
        Publish an event and block until Kafka acknowledges it.

        Uses the event's `run_id` as the message key so all events of a run land on
        one partition (causal ordering). Raises EventPublishError if delivery fails,
        so callers never mistake a lost message for a sent one.
        """
        errors: list[KafkaError] = []

        def on_delivery(err: KafkaError | None, msg: Message) -> None:
            if err is not None:
                errors.append(err)

        try:
            key = (event.run_id or event.event_type).encode("utf-8")
            self.producer.produce(
                topic=self.topic,
                key=key,
                value=event.to_json_bytes(),
                callback=on_delivery,
            )
            pending = self.producer.flush(self.DELIVERY_TIMEOUT_S)
        except Exception as e:
            logger.error(f"Error publishing event {event.event_type}: {e}")
            raise EventPublishError(str(e)) from e

        if errors or pending:
            reason = errors[0] if errors else f"{pending} message(s) not delivered in time"
            logger.error(f"Failed to deliver {event.event_type}: {reason}")
            raise EventPublishError(str(reason))

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
