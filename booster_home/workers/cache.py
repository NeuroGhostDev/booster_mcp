"""Bounded LRU cache для deterministic worker requests."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0


class WorkerCache(Generic[T]):
    """Ключ должен включать content/prompt/model/schema versions."""

    def __init__(self, max_size: int = 256) -> None:
        self.max_size = max(0, max_size)
        self._values: OrderedDict[str, T] = OrderedDict()
        self.stats = CacheStats()

    def get(self, key: str) -> T | None:
        if key in self._values:
            self.stats.hits += 1
            value = self._values.pop(key)
            self._values[key] = value
            return value
        self.stats.misses += 1
        return None

    def set(self, key: str, value: T) -> None:
        if self.max_size == 0:
            return
        self._values.pop(key, None)
        self._values[key] = value
        while len(self._values) > self.max_size:
            self._values.popitem(last=False)
            self.stats.evictions += 1

    def clear(self) -> None:
        self._values.clear()
