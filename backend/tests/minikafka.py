"""
Deterministic in-memory Kafka + crash injection, driving the REAL `SchedulerConsumer.start()` loop.

  MiniKafka     single-partition append-only log + committed offset (Kafka semantics: an uncommitted message is
                redelivered to whoever consumes next; poll() advances the position, commit() the durable offset)
  LogConsumer   the confluent-kafka Consumer surface the scheduler uses: subscribe / poll / commit / seek / close
  MiniBus       EventBus that appends to the log
  Hooks         crash / fault plan shared by bus, consumer and DB session
  Harness       start / crash / restart loop over a real PostgreSQL

Crash points (each fires once, at the n-th time an event of the given type reaches that point):
  before_publish   the handler finished, the child event was NOT yet published        (agent work lost)
  after_publish    the child event is in the log, nothing persisted yet               (duplicate child on redelivery)
  at_commit        result applied in the transaction, the COMMIT never happened       (rollback)
  after_db_commit  PostgreSQL committed, the offset commit never happened             (redelivery of a finished event)
A crash is `Crash(SystemExit)`: a BaseException that no `except Exception` in the scheduler can swallow, exactly
like the process dying.
"""

import threading
import time
from dataclasses import dataclass, field

from app.events.event_bus import EventBus
from app.events.schemas import KafkaEvent
from app.scheduler.consumer import SchedulerConsumer


class Crash(SystemExit):
    """Simulated process death."""


class MiniKafka:
    def __init__(self) -> None:
        self.log: list[bytes] = []
        self.committed = 0
        self.lock = threading.Lock()

    def append(self, raw: bytes) -> int:
        with self.lock:
            self.log.append(raw)
            return len(self.log) - 1

    def duplicate(self, index: int) -> None:
        """Deliver the very same message again (same event_id), like a broker/producer redelivery."""
        with self.lock:
            raw = self.log[index]
        self.append(raw)

    def size(self) -> int:
        with self.lock:
            return len(self.log)

    def events(self) -> list[KafkaEvent]:
        with self.lock:
            return [KafkaEvent.model_validate_json(r) for r in self.log]


class Msg:
    def __init__(self, offset: int, value: bytes):
        self._offset, self._value = offset, value

    def value(self): return self._value
    def error(self): return None
    def offset(self): return self._offset
    def topic(self): return "mini"
    def partition(self): return 0


class ErrMsg:
    """A consumer error event (e.g. broker unavailable): poll() returns it and the loop must survive."""

    class _E:
        def code(self): return -1
        def __str__(self): return "broker transport failure (simulated)"

    def error(self): return self._E()


@dataclass
class CrashSpec:
    point: str
    event_type: str
    nth: int = 1
    seen: int = 0
    fired: bool = False


@dataclass
class Hooks:
    plan: list[CrashSpec] = field(default_factory=list)
    current_type: str | None = None
    fired: list[tuple[str, str]] = field(default_factory=list)
    commit_errors: int = 0          # the next N offset commits raise a (non-crash) Kafka error
    poll_errors: int = 0            # the next N polls return an error event instead of a message
    publish_fail_types: set[str] = field(default_factory=set)

    def arm(self, point: str, event_type: str, nth: int = 1) -> "Hooks":
        self.plan.append(CrashSpec(point, event_type, nth))
        return self

    def match(self, point: str, event_type: str | None) -> bool:
        for spec in self.plan:
            if spec.point == point and spec.event_type == event_type and not spec.fired:
                spec.seen += 1
                if spec.seen == spec.nth:
                    spec.fired = True
                    self.fired.append((point, event_type))
                    return True
        return False


class MiniBus(EventBus):
    def __init__(self, kafka: MiniKafka, hooks: Hooks | None = None):
        self.kafka, self.hooks, self.closed = kafka, hooks or Hooks(), False

    def publish(self, event: KafkaEvent) -> None:
        h = self.hooks
        if h.match("before_publish", h.current_type):
            raise Crash("crash before publish")
        if event.event_type in h.publish_fail_types:
            raise RuntimeError(f"kafka unavailable for {event.event_type}")
        self.kafka.append(event.to_json_bytes())
        if h.match("after_publish", h.current_type):
            raise Crash("crash after publish")

    def close(self) -> None:
        self.closed = True


class LogConsumer:
    def __init__(self, kafka: MiniKafka, hooks: Hooks):
        self.kafka, self.hooks, self.closed = kafka, hooks, False
        self.pos = kafka.committed  # a (re)started consumer resumes from the last COMMITTED offset

    def subscribe(self, topics) -> None:
        pass

    def poll(self, timeout: float = 1.0):
        if self.hooks.poll_errors > 0:
            self.hooks.poll_errors -= 1
            return ErrMsg()
        with self.kafka.lock:
            if self.pos < len(self.kafka.log):
                msg = Msg(self.pos, self.kafka.log[self.pos])
                self.pos += 1
                return msg
        time.sleep(min(timeout, 0.02))
        return None

    def commit(self, message=None, asynchronous: bool = False) -> None:
        if self.hooks.commit_errors > 0:
            self.hooks.commit_errors -= 1
            raise RuntimeError("offset commit failed (simulated broker error)")
        etype = KafkaEvent.model_validate_json(message.value()).event_type
        if self.hooks.match("after_db_commit", etype):
            raise Crash("crash after DB commit, before the offset commit")
        with self.kafka.lock:
            self.kafka.committed = max(self.kafka.committed, message.offset() + 1)

    def seek(self, tp) -> None:
        self.pos = tp.offset

    def close(self) -> None:
        self.closed = True


class HarnessScheduler(SchedulerConsumer):
    """The real scheduler; only records which event is being processed so crash points can target it."""

    def __init__(self, *a, hooks: Hooks, **kw):
        super().__init__(*a, **kw)
        self._hooks = hooks

    def process(self, event: KafkaEvent) -> None:
        self._hooks.current_type = str(event.event_type)
        try:
            super().process(event)
        finally:
            self._hooks.current_type = None


def wait_idle(kafka: MiniKafka, thread: threading.Thread, timeout: float = 60.0) -> str:
    """'idle' when everything is committed and stays so; 'dead' if the scheduler thread died (a crash)."""
    end, stable = time.time() + timeout, 0
    while time.time() < end:
        if not thread.is_alive():
            return "dead"
        with kafka.lock:
            done = kafka.committed >= len(kafka.log)
        stable = stable + 1 if done else 0
        if stable >= 6:
            return "idle"
        time.sleep(0.05)
    raise TimeoutError(f"scheduler did not become idle: committed={kafka.committed} log={kafka.size()}")


class Harness:
    def __init__(self, session_factory, kafka: MiniKafka | None = None, hooks: Hooks | None = None):
        self.sf = session_factory
        self.kafka = kafka or MiniKafka()
        self.hooks = hooks or Hooks()
        self.starts = 0

    def _session_factory(self):
        hooks, sf = self.hooks, self.sf

        def factory():
            s = sf()
            real_commit = s.commit

            def commit():
                if hooks.match("at_commit", hooks.current_type):
                    raise Crash("crash right before the DB commit")
                return real_commit()

            s.commit = commit
            return s
        return factory

    def new_scheduler(self) -> HarnessScheduler:
        return HarnessScheduler(
            "unused", "mini", "g", consumer=LogConsumer(self.kafka, self.hooks),
            event_bus=MiniBus(self.kafka, self.hooks), session_factory=self._session_factory(), hooks=self.hooks)

    def start(self):
        self.starts += 1
        sched = self.new_scheduler()
        thread = threading.Thread(target=sched.start, daemon=True)
        thread.start()
        return sched, thread

    def api_bus(self) -> MiniBus:
        return MiniBus(self.kafka, Hooks())  # the API side never crashes

    def run_until_done(self, max_restarts: int = 30, timeout: float = 90.0) -> int:
        """Run the scheduler until the log is fully committed, restarting it after every simulated crash."""
        crashes = 0
        while True:
            sched, thread = self.start()
            state = wait_idle(self.kafka, thread, timeout)
            if state == "dead":
                crashes += 1
                assert crashes <= max_restarts, "too many restarts: the workflow is not converging"
                continue
            sched.stop()
            thread.join(10)
            return crashes
