"""
Entry point for the Scheduler consumer process.
Can be run via: python -m app.scheduler
"""

import logging
import signal
import sys
import threading

from app.core.config import settings
from app.scheduler.consumer import SchedulerConsumer

# Configure basic logging for the scheduler process
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> None:
    consumer = SchedulerConsumer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_TOPIC,
        group_id=settings.KAFKA_CONSUMER_GROUP,
    )

    # Handle graceful shutdown on SIGINT/SIGTERM
    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        # Run stop in a new thread in case we are blocked, though boolean flag usually suffices
        threading.Thread(target=consumer.stop).start()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Start blocks until consumer.running becomes False
    consumer.start()
    
    logger.info("Scheduler process terminated.")


if __name__ == "__main__":
    main()
