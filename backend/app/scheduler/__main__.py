"""
Entry point for the Scheduler consumer process.
Can be run via: python -m app.scheduler
"""

import logging
import signal
import sys
import threading

from app.core.config import settings
from app.core.redaction import install_log_redaction
from app.scheduler.consumer import SchedulerConsumer
from agents.llm.factory import log_llm_config
from app.memory.embeddings import get_embedding_service

# Configure basic logging for the scheduler process
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
install_log_redaction()  # provider errors can echo credentials; scrub every log record
logger = logging.getLogger(__name__)


def report_stale_runs() -> None:
    """Startup hint (read-only): runs that look abandoned. Never changes anything."""
    try:
        from datetime import timedelta
        from app.db.database import SessionLocal
        from app.services.run_service import find_stale_runs
        with SessionLocal() as db:
            stale = find_stale_runs(db, timedelta(minutes=settings.STALE_RUN_MINUTES))
        if stale:
            logger.warning("%d run(s) are 'running' with no events for over %d min (not modified): %s",
                           len(stale), settings.STALE_RUN_MINUTES, ", ".join(r["run_id"] for r in stale[:10]))
    except Exception as e:
        logger.warning("Stale-run check skipped: %s", type(e).__name__)


def main() -> None:
    log_llm_config()
    embeddings = get_embedding_service()
    if embeddings is None:
        logger.info("Embedding provider: none (Queen memory disabled)")
    else:
        embeddings.warmup()  # fail fast: load the model and check the vector size now, not mid-run
        logger.info(f"Embedding provider: {embeddings.description} | vector DB: PostgreSQL + pgvector")

    report_stale_runs()
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
