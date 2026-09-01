"""Small thread-safe TTL cache for generation-bound read-only results."""

from __future__ import annotations

import copy
import json
import threading
import time
from collections import OrderedDict
from typing import Any


class ReadOnlyCache:
    """Cache results only within one repository generation."""

    def __init__(self, max_entries: int = 128, ttl_seconds: float = 30.0) -> None:
        if max_entries < 1 or ttl_seconds <= 0:
            raise ValueError("cache bounds must be positive")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[tuple[str, str, str, str], tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def key(
        repo_id: str, generation_id: str, operation: str, normalized_args: Any
    ) -> tuple[str, str, str, str]:
        args = json.dumps(
            normalized_args,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return repo_id, generation_id, operation, args

    def get(self, key: tuple[str, str, str, str]) -> Any | None:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return copy.deepcopy(value)

    def set(self, key: tuple[str, str, str, str], value: Any) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + self.ttl_seconds, copy.deepcopy(value))
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def invalidate_repo(self, repo_id: str, generation_id: str | None = None) -> None:
        with self._lock:
            stale = [
                key
                for key in self._items
                if key[0] == repo_id and (generation_id is None or key[1] != generation_id)
            ]
            for key in stale:
                self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
