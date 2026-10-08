"""
Kafka consumer for the Scheduler.

Processing contract for every consumed event (at-least-once + application-level dedup):

    1. duplicate?  events.id == event_id already exists  -> skip, commit offset
    2. run missing or already terminal                    -> skip, commit offset
    3. run the handler (agent call)                       -> Outcome(next_event, db effects)
    4. publish the next event (blocks until Kafka acks)
    5. in ONE DB transaction: insert the consumed event row + apply effects
    6. commit the Kafka offset

Handler/publish failure (3-4): publish `run.failed`, persist the failing event, commit the
offset. The failure is recorded instead of retried, so there is no retry storm.
Infrastructure failure (DB down, offset commit): the offset is NOT committed; the consumer
seeks back to the message and retries after a pause.

Guardian revision loop (Phase 3): review.completed is the loop controller.
    approved        -> run.completed
    needs_revision  -> revision.requested (revision_count < MAX_REVISIONS) -> Builder revises -> tasks.generated
                       -> Guardian re-reviews -> review.completed ...   else run.failed MAX_REVISIONS_EXCEEDED
    rejected        -> run.failed
Every event carries `revision_number` (0 = original Builder output). Revision rows (run_revisions) and revised
tasks are written in the same transaction as the consumed event row, so all of it is idempotent under redelivery.

Error taxonomy (Phase 5). Every failure is exactly one of:
  * agent / handler error (incl. timeouts, provider errors, malformed output, publish failure)
        -> run.failed, the failing event is recorded, the offset is committed (no retry storm)
  * transient infrastructure error (PostgreSQL connection/timeout/deadlock, offset commit failure)
        -> nothing is committed, the message is redelivered after RETRY_PAUSE_S (bounded by the outage)
  * permanent persistence error (constraint/data error while saving the result)
        -> "poison event": the run is failed directly in PostgreSQL, the message is committed. A poison event can
           never block the consumer, and never retries forever.

Downstream event ids are derived from the parent event id (uuid5), so if the process
crashes after step 4 and the parent is redelivered, the re-published child carries the same
event_id and is dropped by step 1. The only duplicated work in that crash window is the agent
call itself.
"""

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict
from uuid import UUID, uuid5

from confluent_kafka import Consumer, KafkaError, TopicPartition
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.kafka_config import kafka_security_config
from app.core.metrics import metrics
from app.core.redaction import redact_secrets
from app.db.database import SessionLocal
from app.events.event_bus import EventBus
from app.events.event_types import EventTypes
from app.events.kafka_event_bus import KafkaEventBus
from app.events.schemas import KafkaEvent
from app.models import Run
from app.services import event_service, run_service
from app.services.run_service import RunStatus
from app.telemetry.contract import NOTIFY_CHANNEL

from agents.queen.service import QueenService
from agents.architect.service import ArchitectService
from agents.scout.service import ScoutService
from agents.builder.service import BuilderService
from agents.guardian.service import GuardianService
from agents.guardian.revision import RevisionRequest, build_revision_request, guardian_feedback
from agents.guardian.schemas import ValidationReport
from agents.queen.schemas import Strategy
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import ResearchReport
from agents.builder.schemas import TaskGraph

logger = logging.getLogger(__name__)

RETRY_PAUSE_S = 5.0
METRICS_LOG_EVERY_S = 60.0

# Which stage was executing when a given event was being handled (for run.failed payloads).
_STAGE = {
    EventTypes.RUN_CREATED: "queen",
    EventTypes.STRATEGY_CREATED: "architect",
    EventTypes.ARCHITECTURE_CREATED: "scout",
    EventTypes.RESEARCH_COMPLETED: "builder",
    EventTypes.TASKS_GENERATED: "guardian",
    EventTypes.REVIEW_COMPLETED: "scheduler",
    EventTypes.REVISION_REQUESTED: "builder",
}

# Events that carry `revision_number` and must be checked against the run's current revision
_REVISION_AWARE = (EventTypes.REVISION_REQUESTED, EventTypes.TASKS_GENERATED, EventTypes.REVIEW_COMPLETED)


@dataclass
class Outcome:
    """What a handler wants done: an event to publish and DB changes to commit with the event row."""
    next_event: KafkaEvent | None = None
    apply: Callable[[Session], None] | None = None
    failure: dict | None = None  # set when this outcome records an agent/handler failure: {"stage", "error_type"}
    direct_failure: bool = False  # the run.failed was written straight to PostgreSQL (Kafka unavailable)


def _is_transient_db_error(exc: BaseException) -> bool:
    """Connection loss, timeouts, deadlocks: retrying the same message can succeed. Data errors cannot."""
    return isinstance(exc, (OperationalError, InterfaceError)) or bool(getattr(exc, "connection_invalidated", False))


def _child_event(parent: KafkaEvent, event_type: EventTypes, source: str, payload: dict) -> KafkaEvent:
    return KafkaEvent(
        event_id=uuid5(parent.event_id, str(event_type.value)),
        event_type=event_type.value,
        source=source,
        run_id=parent.run_id,
        payload=payload,
    )


def _safe_message(exc: Exception) -> str:
    return redact_secrets(str(exc))[:500]


class SchedulerConsumer:
    """Consumes events from Kafka and drives the workflow: decides which agent runs next."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        *,
        consumer: Consumer | None = None,
        event_bus: EventBus | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.topic = topic
        self.running = False
        self._stop_event = threading.Event()
        self.session_factory = session_factory
        self.event_bus = event_bus or KafkaEventBus(bootstrap_servers, topic)

        logger.info(f"Initializing SchedulerConsumer for topic '{self.topic}' (group: {group_id})")
        self.consumer = consumer or Consumer({**kafka_security_config(),
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            # Offsets are committed manually, only after an event is fully processed.
            "enable.auto.commit": False,
            # Agent chains can take minutes; don't get kicked out of the group mid-handler.
            "max.poll.interval.ms": 1_800_000,
        })

        self._handlers: Dict[str, Callable[[KafkaEvent], Outcome]] = {
            EventTypes.RUN_CREATED: self._handle_run_created,
            EventTypes.STRATEGY_CREATED: self._handle_strategy_created,
            EventTypes.ARCHITECTURE_CREATED: self._handle_architecture_created,
            EventTypes.RESEARCH_COMPLETED: self._handle_research_completed,
            EventTypes.TASKS_GENERATED: self._handle_tasks_generated,
            EventTypes.REVIEW_COMPLETED: self._handle_review_completed,
            EventTypes.REVISION_REQUESTED: self._handle_revision_requested,
            EventTypes.RUN_COMPLETED: self._handle_run_completed,
            EventTypes.RUN_FAILED: self._handle_run_failed,
        }

    # ── Handlers: pure "do the work, describe the result" ───────────────

    def _handle_run_created(self, event: KafkaEvent) -> Outcome:
        """Queen: Goal -> Strategy"""
        goal = event.payload["goal"]
        result = asyncio.run(QueenService().generate_strategy(
            UUID(event.run_id), goal, event.payload["project_id"], str(event.event_id)))
        return Outcome(_child_event(
            event, EventTypes.STRATEGY_CREATED, "queen",
            {"goal": goal, "strategy": result.model_dump(mode="json")},
        ))

    def _handle_strategy_created(self, event: KafkaEvent) -> Outcome:
        """Architect: Strategy -> ArchitecturePlan"""
        goal = event.payload["goal"]
        strategy = Strategy.model_validate(event.payload["strategy"])
        result = asyncio.run(ArchitectService().generate_plan(UUID(event.run_id), goal, strategy))
        return Outcome(_child_event(
            event, EventTypes.ARCHITECTURE_CREATED, "architect",
            {"goal": goal, "architecture_plan": result.model_dump(mode="json")},
        ))

    def _handle_architecture_created(self, event: KafkaEvent) -> Outcome:
        """Scout: ArchitecturePlan -> ResearchReport"""
        goal = event.payload["goal"]
        plan = ArchitecturePlan.model_validate(event.payload["architecture_plan"])
        result = asyncio.run(ScoutService().generate_research(UUID(event.run_id), goal, plan))
        return Outcome(_child_event(
            event, EventTypes.RESEARCH_COMPLETED, "scout",
            {**event.payload, "research_report": result.model_dump(mode="json")},
        ))

    def _handle_research_completed(self, event: KafkaEvent) -> Outcome:
        """Builder: Plan + Research -> TaskGraph (persisted to `tasks`)"""
        goal = event.payload["goal"]
        plan = ArchitecturePlan.model_validate(event.payload["architecture_plan"])
        report = ResearchReport.model_validate(event.payload["research_report"])
        result = asyncio.run(BuilderService().generate_task_graph(UUID(event.run_id), goal, plan, report))
        graph = result.model_dump(mode="json")
        return Outcome(
            _child_event(
                event, EventTypes.TASKS_GENERATED, "builder",
                {**event.payload, "task_graph": graph, "revision_number": 0},
            ),
            apply=lambda db: run_service.add_tasks_from_graph(db, event.run_id, graph, revision_number=0),
        )

    def _handle_tasks_generated(self, event: KafkaEvent) -> Outcome:
        """Guardian: Plan + Research + (latest) Tasks -> ValidationReport. Reviews exactly the graph in this event."""
        goal = event.payload["goal"]
        plan = ArchitecturePlan.model_validate(event.payload["architecture_plan"])
        report = ResearchReport.model_validate(event.payload["research_report"])
        graph = TaskGraph.model_validate(event.payload["task_graph"])
        n = int(event.payload.get("revision_number", 0))
        previous_changes = event.payload["revision"]["requested_changes"] if n else []
        if n:
            logger.info("Guardian reviewing revision=%d | run=%s event=%s", n, event.run_id, event.event_id)
        result = asyncio.run(GuardianService().generate_review(
            UUID(event.run_id), goal, plan, report, graph,
            revision_number=n, previous_requested_changes=previous_changes))
        return Outcome(_child_event(
            event, EventTypes.REVIEW_COMPLETED, "guardian",
            {**event.payload, "validation_report": result.model_dump(mode="json")},
        ))

    def _handle_review_completed(self, event: KafkaEvent) -> Outcome:
        """
        Guardian verdict -> next step. The loop bound (MAX_REVISIONS) is enforced here, in code:
          approved        -> run.completed
          needs_revision  -> revision.requested, or run.failed (MAX_REVISIONS_EXCEEDED) once
                             revision_count >= MAX_REVISIONS
          rejected        -> run.failed (ReviewRejected)
        """
        report = ValidationReport.model_validate(event.payload["validation_report"])  # strict re-validation
        n = int(event.payload.get("revision_number", 0))  # 0 = original output; N = output of revision N
        verdict = report.overall_verdict
        run_id, review_id = event.run_id, str(event.event_id)
        if verdict not in ("approved", "needs_revision", "rejected"):  # never guess: an unknown verdict is a failure
            raise ValueError(f"Guardian returned an invalid verdict {verdict!r}")
        logger.info("Guardian verdict: %s | run=%s revision=%d event=%s", verdict, run_id, n, review_id)

        def mark(status: str):
            return lambda db: run_service.set_revision_status(db, run_id, n, status, review_event_id=review_id)

        if verdict == "approved":
            if n:
                logger.info("Revision approved | run=%s revision=%d", run_id, n)
            return Outcome(_child_event(
                event, EventTypes.RUN_COMPLETED, "scheduler",
                {"run_id": run_id, "verdict": verdict, "summary": report.summary, "revision_count": n},
            ), apply=mark("approved"))

        failure = {
            "run_id": run_id, "failed_stage": "guardian", "verdict": verdict, "revision_count": n,
            "max_revisions": settings.MAX_REVISIONS, "feedback": guardian_feedback(report),
            "requested_changes": report.recommendations,
        }
        if verdict == "rejected":
            return Outcome(_child_event(
                event, EventTypes.RUN_FAILED, "scheduler",
                {**failure, "error_type": "ReviewRejected",
                 "message": f"Guardian verdict 'rejected': {report.summary}"[:500]},
            ), apply=mark("rejected"))

        # needs_revision
        if n >= settings.MAX_REVISIONS:
            logger.warning("Maximum revisions reached | run=%s revisions=%d max=%d", run_id, n, settings.MAX_REVISIONS)
            return Outcome(_child_event(
                event, EventTypes.RUN_FAILED, "scheduler",
                {**failure, "error_type": "MAX_REVISIONS_EXCEEDED",
                 "message": (f"Guardian still asked for changes after {n} revision(s) "
                             f"(MAX_REVISIONS={settings.MAX_REVISIONS}): {report.summary}")[:500]},
            ), apply=mark("needs_revision"))

        request = build_revision_request(report, run_id, review_id, n + 1, settings.MAX_REVISIONS)
        logger.info("Revision requested: revision=%d | run=%s review_event=%s revision_id=%s",
                    request.revision_number, run_id, review_id, request.revision_id)

        def apply(db: Session) -> None:
            run_service.set_revision_status(db, run_id, n, "needs_revision", review_event_id=review_id)
            run_service.add_revision(db, request)

        payload = {k: event.payload[k] for k in ("goal", "architecture_plan", "research_report", "task_graph")}
        payload.update(revision_number=request.revision_number, revision=request.model_dump(mode="json"))
        return Outcome(_child_event(event, EventTypes.REVISION_REQUESTED, "guardian", payload), apply=apply)

    def _handle_revision_requested(self, event: KafkaEvent) -> Outcome:
        """Builder: previous TaskGraph + Guardian feedback -> revised TaskGraph (persisted as revision N tasks)."""
        request = RevisionRequest.model_validate(event.payload["revision"])
        goal = event.payload["goal"]
        plan = ArchitecturePlan.model_validate(event.payload["architecture_plan"])
        report = ResearchReport.model_validate(event.payload["research_report"])
        previous = TaskGraph.model_validate(event.payload["task_graph"])
        logger.info("Builder revision started | run=%s revision=%d event=%s", event.run_id, request.revision_number, event.event_id)
        result = asyncio.run(BuilderService().revise_task_graph(
            UUID(event.run_id), goal, plan, report, previous, request))
        graph = result.model_dump(mode="json")
        child = _child_event(
            event, EventTypes.TASKS_GENERATED, "builder",
            {**event.payload, "task_graph": graph, "revision_number": request.revision_number},
        )
        logger.info("Builder revision completed | run=%s revision=%d tasks=%d", event.run_id,
                    request.revision_number, len(graph["tasks"]))

        def apply(db: Session) -> None:
            run_service.add_tasks_from_graph(db, event.run_id, graph, revision_number=request.revision_number)
            run_service.set_revision_status(db, event.run_id, request.revision_number, "revised",
                                            tasks_event_id=str(child.event_id))

        return Outcome(child, apply=apply)

    def _handle_run_completed(self, event: KafkaEvent) -> Outcome:
        return Outcome(apply=lambda db: run_service.finish_run(db, event.run_id, RunStatus.COMPLETED))

    def _handle_run_failed(self, event: KafkaEvent) -> Outcome:
        return Outcome(apply=lambda db: run_service.finish_run(db, event.run_id, RunStatus.FAILED))

    # ── Failure path ────────────────────────────────────────────────────

    @staticmethod
    def _failed_event(event: KafkaEvent, exc: Exception) -> KafkaEvent:
        return _child_event(
            event, EventTypes.RUN_FAILED, "scheduler",
            {
                "run_id": event.run_id,
                "failed_stage": _STAGE.get(event.event_type, "scheduler"),
                "error_type": type(exc).__name__,
                "message": _safe_message(exc),
            },
        )

    def _fail(self, event: KafkaEvent, exc: Exception) -> Outcome:
        """Record a handler failure as run.failed. Never raises for Kafka problems."""
        stage = _STAGE.get(event.event_type, "scheduler")
        logger.error("Handler failed | stage=%s type=%s run=%s event=%s: %s", stage, type(exc).__name__,
                     event.run_id, event.event_id, _safe_message(exc), exc_info=True)
        failed = self._failed_event(event, exc)
        info = {"stage": stage, "error_type": type(exc).__name__}
        try:
            self.event_bus.publish(failed)
            return Outcome(failure=info)  # run.failed is consumed later and sets the run to FAILED
        except Exception as pub_exc:
            # Kafka is unavailable: still make the failure durable in PostgreSQL.
            logger.error("Could not publish run.failed (%s); recording it directly in the DB | run=%s event=%s",
                         type(pub_exc).__name__, event.run_id, event.event_id)

            def apply(db: Session) -> None:
                event_service.add_kafka_event(db, failed)
                run_service.finish_run(db, event.run_id, RunStatus.FAILED)
            return Outcome(apply=apply, failure=info, direct_failure=True)

    # ── Core ────────────────────────────────────────────────────────────

    def process(self, event: KafkaEvent) -> None:
        """
        Process one event. Returns normally when the message may be committed (processed, duplicate, ignored,
        recorded as failed, or isolated as a poison event); raises ONLY for transient infrastructure errors,
        which must be retried.
        """
        started = time.monotonic()
        rev = event.payload.get("revision_number")
        with self.session_factory() as db:
            if event_service.event_exists(db, str(event.event_id)):
                metrics.inc("events_duplicate")
                logger.info("Duplicate event skipped | type=%s run=%s event=%s", event.event_type, event.run_id, event.event_id)
                return

            run = db.get(Run, event.run_id) if event.run_id else None
            if run is None:
                metrics.inc("events_dropped", reason="unknown_run")
                logger.error("Event for an unknown run dropped | type=%s run=%s event=%s", event.event_type, event.run_id, event.event_id)
                return
            if run.status in RunStatus.TERMINAL:
                metrics.inc("events_ignored", reason="terminal_run")
                logger.info("Run already %s; ignoring | type=%s run=%s event=%s", run.status, event.event_type, run.id, event.event_id)
                return

            outcome = self._execute(db, event)
            if outcome is None:  # stale revision event: ignored on purpose
                return
            self._persist(db, event, outcome)
        metrics.observe("kafka_processing_seconds", time.monotonic() - started, event_type=str(event.event_type))

    def _execute(self, db: Session, event: KafkaEvent) -> Outcome | None:
        """Run the handler and publish its result. Agent/handler errors become a failure Outcome."""
        handler = self._handlers.get(event.event_type)
        if handler is None:
            logger.warning("No handler for event type; recording only | type=%s run=%s event=%s",
                           event.event_type, event.run_id, event.event_id)
            return Outcome()
        rev = event.payload.get("revision_number")
        logger.info("[SCHEDULER] %s run=%s event=%s rev=%s", event.event_type, event.run_id, event.event_id, rev)
        try:
            if isinstance(rev, int) and event.event_type in _REVISION_AWARE:
                current = run_service.current_revision(db, event.run_id)
                if rev < current:  # superseded by a newer revision: never act on it
                    metrics.inc("events_ignored", reason="stale_revision")
                    logger.warning("Ignoring stale %s for revision=%d (current revision=%d) | run=%s event=%s",
                                   event.event_type, rev, current, event.run_id, event.event_id)
                    return None
                if rev > current:
                    raise RuntimeError(f"revision state inconsistent: event is for revision {rev} "
                                       f"but the run's latest recorded revision is {current}")
            with metrics.timer("agent_latency_seconds", agent=_STAGE.get(event.event_type, "scheduler")):
                outcome = handler(event)
        except Exception as exc:
            if _is_transient_db_error(exc):  # the DATABASE hiccuped, not the workflow: retry the message, keep the run
                raise
            return self._fail(event, exc)
        # Publishing is INFRASTRUCTURE, not agent work: a broker error must never fail the run. It propagates to the
        # consume loop, which retries the same message (nothing persisted, agent result re-derived on retry).
        if outcome.next_event is not None:
            self.event_bus.publish(outcome.next_event)
        return outcome

    def _persist(self, db: Session, event: KafkaEvent, outcome: Outcome) -> None:
        """One transaction: consumed-event row + effects. Transient errors retry; permanent ones isolate the event."""
        try:
            event_service.add_kafka_event(db, event)
            if outcome.apply is not None:
                outcome.apply(db)
            db.commit()
        except Exception as exc:
            db.rollback()
            if _is_transient_db_error(exc):
                raise
            if event_service.event_exists(db, str(event.event_id)):
                # Lost a race with another worker that persisted this very event first: it is a duplicate, not a
                # poison event. Nothing to do (its result is already durable; the child event id is deterministic).
                metrics.inc("events_duplicate")
                logger.info("Duplicate event (concurrent worker won) | type=%s run=%s event=%s",
                            event.event_type, event.run_id, event.event_id)
                return
            self._isolate_poison_event(db, event, exc)
            return
        self._after_commit(db, event, outcome)

    def _isolate_poison_event(self, db: Session, event: KafkaEvent, exc: Exception) -> None:
        """
        Saving the result failed for a reason retrying cannot fix (constraint/data error, bug). Fail the run directly
        in PostgreSQL (no Kafka round trip, so downstream events already published see a terminal run) and let the
        offset be committed: one bad event must not block every other run behind it.
        """
        metrics.inc("poison_events")
        logger.error("Permanent persistence error; failing the run | type=%s run=%s event=%s: %s: %s",
                     event.event_type, event.run_id, event.event_id, type(exc).__name__, _safe_message(exc))
        failed = self._failed_event(event, exc)
        try:
            event_service.add_kafka_event(db, event)
            event_service.add_kafka_event(db, failed)
            run_service.finish_run(db, event.run_id, RunStatus.FAILED)
            db.commit()
        except Exception as exc2:
            db.rollback()
            if _is_transient_db_error(exc2):
                raise
            metrics.inc("poison_events_unrecorded")
            logger.critical("Could not even record the failure; SKIPPING the message so it cannot block the consumer "
                            "(the run stays 'running' and is reported by stale-run detection) | run=%s event=%s: %s",
                            event.run_id, event.event_id, type(exc2).__name__)
            return
        self._after_commit(db, event, Outcome(failure={"stage": _STAGE.get(event.event_type, "scheduler"),
                                                       "error_type": type(exc).__name__}, direct_failure=True))

    def _after_commit(self, db: Session, event: KafkaEvent, outcome: Outcome) -> None:
        """Everything that must only happen once the transaction is durable."""
        self._notify_committed(db, event.run_id)
        t = str(event.event_type)
        metrics.inc("events_processed", event_type=t)
        if t == EventTypes.RUN_CREATED.value:
            metrics.inc("runs_started")
        elif t == EventTypes.RUN_COMPLETED.value:
            metrics.inc("runs_completed")
        elif t == EventTypes.RUN_FAILED.value:
            metrics.inc("runs_failed")
        if outcome.failure:
            metrics.inc("agent_failures", stage=outcome.failure["stage"])
            if outcome.direct_failure:
                metrics.inc("runs_failed")
        nxt = outcome.next_event
        if nxt is not None and nxt.event_type == EventTypes.REVISION_REQUESTED.value:
            metrics.inc("revisions_requested")
        if nxt is not None and nxt.event_type == EventTypes.RUN_FAILED.value and \
                nxt.payload.get("error_type") == "MAX_REVISIONS_EXCEEDED":
            metrics.inc("revision_limit_failures")

    @staticmethod
    def _notify_committed(db: Session, run_id: str) -> None:
        """
        Tell WebSocket telemetry (API process) that this run has new committed events. Best effort and strictly
        AFTER the commit: a failure here is logged and ignored, and can never affect the workflow or the offset.
        """
        try:
            db.execute(text("SELECT pg_notify(:channel, :run_id)"), {"channel": NOTIFY_CHANNEL, "run_id": run_id})
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Telemetry notify failed (ignored): %s", type(exc).__name__)

    def start(self) -> None:
        """Poll loop. Blocks until stop() is called."""
        self.consumer.subscribe([self.topic])
        self.running = True
        logger.info(f"SchedulerConsumer started, listening on {self.topic}...")
        retries: dict[str, int] = {}
        last_metrics_log = time.monotonic()

        try:
            while self.running:
                if time.monotonic() - last_metrics_log >= METRICS_LOG_EVERY_S:
                    self._log_metrics()
                    last_metrics_log = time.monotonic()
                msg = self.consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        metrics.inc("consumer_errors")
                        logger.error(f"Consumer error: {msg.error()}")
                    continue

                try:
                    event = KafkaEvent.model_validate(json.loads(msg.value().decode("utf-8")))
                except (ValueError, ValidationError, AttributeError) as e:
                    # Poison message: cannot be tied to a run and never will parse. Skip it.
                    metrics.inc("events_dropped", reason="undecodable")
                    logger.error(f"Dropping undecodable message at offset {msg.offset()}: {e}")
                    self.consumer.commit(message=msg, asynchronous=False)
                    continue

                key = f"{msg.partition()}:{msg.offset()}"
                try:
                    self.process(event)
                    self.consumer.commit(message=msg, asynchronous=False)
                    retries.pop(key, None)
                except Exception as e:
                    # Transient infrastructure failure: leave the offset uncommitted and retry this message.
                    attempts = retries[key] = retries.get(key, 0) + 1
                    metrics.inc("infra_retries")
                    logger.error("Infrastructure error, will retry in %ss (attempt %d) | type=%s run=%s event=%s: %s",
                                 RETRY_PAUSE_S, attempts, event.event_type, event.run_id, event.event_id,
                                 type(e).__name__, exc_info=(attempts == 1))
                    self.consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                    self._stop_event.wait(RETRY_PAUSE_S)  # interruptible by stop()
        except KeyboardInterrupt:
            logger.info("SchedulerConsumer interrupted by user")
        finally:
            logger.info("Closing SchedulerConsumer...")
            self._log_metrics()
            self.consumer.close()
            self.event_bus.close()

    @staticmethod
    def _log_metrics() -> None:
        snap = metrics.snapshot()
        if snap["counters"] or snap["timings"]:
            logger.info("metrics %s", json.dumps(snap, separators=(",", ":")))

    def stop(self) -> None:
        """Signal the polling loop to stop gracefully (also wakes it from a retry pause)."""
        self.running = False
        self._stop_event.set()
