"""Небольшой bounded in-process registry метрик."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class MetricsRegistry:
    """Счётчики и bounded latency samples без unbounded labels."""

    def __init__(self, max_samples: int = 256) -> None:
        self.max_samples = max(1, max_samples)
        self._counters: defaultdict[str, int] = defaultdict(int)
        self._latencies: defaultdict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, seconds: float) -> None:
        with self._lock:
            samples = self._latencies[name]
            samples.append(max(0.0, float(seconds)))
            del samples[: -self.max_samples]

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter() - started)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "latencies": {
                    key: {
                        "count": len(values),
                        "last_seconds": values[-1] if values else None,
                        "avg_seconds": sum(values) / len(values) if values else None,
                    }
                    for key, values in self._latencies.items()
                },
            }
