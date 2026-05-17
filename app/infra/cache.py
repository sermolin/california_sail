"""In-memory TTL cache adapter."""
from __future__ import annotations

import time
from typing import Generic, TypeVar

V = TypeVar("V")


class TTLCache(Generic[V]):
    """Simple in-memory cache with per-entry TTL and a max-size eviction policy."""

    def __init__(self, ttl_seconds: float = 900, max_size: int = 100):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._data: dict[str, tuple[float, V]] = {}

    def get(self, key: str) -> V | None:
        """Return value if present and not expired, else None."""
        if key not in self._data:
            return None
        expires_at, value = self._data[key]
        if time.monotonic() > expires_at:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: V, ttl_seconds: float | None = None) -> None:
        """Store value. Evicts the oldest entry when at max_size."""
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        expires_at = time.monotonic() + ttl
        if key in self._data:
            self._data[key] = (expires_at, value)
            return
        while len(self._data) >= self._max_size and self._data:
            oldest = min(self._data, key=lambda k: self._data[k][0])
            del self._data[oldest]
        self._data[key] = (expires_at, value)

    def clear(self) -> None:
        """Remove all entries."""
        self._data.clear()
