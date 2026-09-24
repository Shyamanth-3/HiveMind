"""
Lightweight in-process operational metrics: counters and latency summaries. No external system.

Each process (API, Scheduler) has its own registry. The Scheduler logs a snapshot periodically and on shutdown;
the API exposes its own registry plus database-derived totals at /health/metrics. Metric names are plain strings
with optional labels, e.g. metrics.inc("agent_failures", stage="scout").
"""

import threading
import time
from contextlib import contextmanager
from typing import Iterator


def _key(name: str, labels: dict[str, str]) -> str:
    return name if not labels else f"{name}{{" + ",".join(f"{k}={v}" for k, v in sorted(labels.items())) + "}"


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {}
        self._timings: dict[str, dict[str, float]] = {}

    def inc(self, name: str, value: float = 1, **labels: str) -> None:
        k = _key(name, labels)
        with self._lock:
            self._counters[k] = self._counters.get(k, 0) + value

    def observe(self, name: str, seconds: float, **labels: str) -> None:
        k = _key(name, labels)
        with self._lock:
            t = self._timings.setdefault(k, {"count": 0, "sum": 0.0, "max": 0.0})
            t["count"] += 1
            t["sum"] += seconds
            t["max"] = max(t["max"], seconds)

    @contextmanager
    def timer(self, name: str, **labels: str) -> Iterator[None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.observe(name, time.monotonic() - start, **labels)

    def get(self, name: str, **labels: str) -> float:
        with self._lock:
            return self._counters.get(_key(name, labels), 0)

    def snapshot(self) -> dict:
        with self._lock:
            timings = {
                k: {"count": int(t["count"]), "avg_s": round(t["sum"] / t["count"], 4), "max_s": round(t["max"], 4)}
                for k, t in self._timings.items()
            }
            return {"counters": dict(sorted(self._counters.items())), "timings": dict(sorted(timings.items()))}

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._timings.clear()


metrics = Metrics()
