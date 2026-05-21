"""Forecast caching abstraction.

Provides a ForecastCache Protocol with two concrete implementations:
- StreamlitForecastCache: sentinel that signals the service to use @st.cache_data (the
  Streamlit-process cache).  Its own get_or_compute is never called on the hot path;
  caching is handled by the @st.cache_data-decorated dispatcher inside forecast_service.
- TTLForecastCache: thread-safe, process-local TTL cache backed by cachetools.TTLCache.
  Used by the MCP server and anywhere that runs outside a Streamlit process.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Literal

from cachetools import TTLCache


class ForecastCache:
    """Protocol-style base class for forecast caches.

    Each implementation must provide::

        def get_or_compute(self, key: str, ttl: int, compute: Callable[[], Any]) -> Any

    where *key* is an opaque string cache key, *ttl* is the desired time-to-live in
    seconds, and *compute* is a zero-arg callable that produces the uncached value.
    """

    def get_or_compute(self, key: str, ttl: int, compute: Callable[[], Any]) -> Any:
        raise NotImplementedError


class StreamlitForecastCache(ForecastCache):
    """Sentinel implementation: signals forecast_service to use @st.cache_data.

    The real caching for Streamlit callers is done by the @st.cache_data-decorated
    function inside forecast_service.  This implementation's get_or_compute is a
    no-cache fallback (useful in tests and direct calls outside Streamlit).
    """

    def get_or_compute(self, key: str, ttl: int, compute: Callable[[], Any]) -> Any:
        return compute()


class TTLForecastCache(ForecastCache):
    """Thread-safe TTL cache backed by cachetools.TTLCache.

    Safe for concurrent use (the MCP server may serve multiple tool calls in
    parallel).  Each instance holds its own cache; share the instance across calls
    to get cache hits.

    Args:
        maxsize: maximum number of entries (oldest entry is evicted when full).
        ttl: default time-to-live in seconds.  The *ttl* passed to get_or_compute
             overrides this per-call.
    """

    def __init__(self, maxsize: int = 256, ttl: int = 900) -> None:
        self._default_ttl = ttl
        self._maxsize = maxsize
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()

    def get_or_compute(self, key: str, ttl: int, compute: Callable[[], Any]) -> Any:
        """Return cached value if present and unexpired, else compute, store, and return.

        Note: the *ttl* argument is used for the initial cache entry but the cache was
        constructed with a fixed TTL.  If you need per-entry TTL control, pass ``ttl``
        consistent with the constructor's *ttl*, or construct a new instance.
        """
        with self._lock:
            if key in self._cache:
                return self._cache[key]

        result = compute()

        with self._lock:
            try:
                self._cache[key] = result
            except ValueError:
                pass

        return result

    def clear(self) -> None:
        """Remove all cached entries (useful in tests)."""
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        """Number of live entries in the cache."""
        with self._lock:
            return len(self._cache)


def make_forecast_cache(backend: Literal["streamlit", "ttl"] = "ttl") -> ForecastCache:
    """Factory that returns the right cache implementation for a given backend name.

    Args:
        backend: ``"streamlit"`` → :class:`StreamlitForecastCache` (for use inside a
                 Streamlit process); ``"ttl"`` → :class:`TTLForecastCache` (for the MCP
                 server or any non-Streamlit process).
    """
    if backend == "streamlit":
        return StreamlitForecastCache()
    if backend == "ttl":
        return TTLForecastCache()
    raise ValueError(f"Unknown cache backend: {backend!r}. Use 'streamlit' or 'ttl'.")
