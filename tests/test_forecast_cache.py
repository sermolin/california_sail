"""Tests for app/infra/forecast_cache.py."""
import time
from unittest.mock import MagicMock

import pytest

from app.infra.forecast_cache import (
    ForecastCache,
    StreamlitForecastCache,
    TTLForecastCache,
    make_forecast_cache,
)


# ---------------------------------------------------------------------------
# Protocol compliance helpers
# ---------------------------------------------------------------------------

def _assert_protocol_compliant(cache: ForecastCache) -> None:
    """Verify that *cache* has the required get_or_compute method."""
    assert hasattr(cache, "get_or_compute"), "cache must implement get_or_compute"
    assert callable(cache.get_or_compute)


# ---------------------------------------------------------------------------
# StreamlitForecastCache
# ---------------------------------------------------------------------------

class TestStreamlitForecastCache:
    def test_protocol_compliant(self):
        cache = StreamlitForecastCache()
        _assert_protocol_compliant(cache)

    def test_get_or_compute_calls_compute(self):
        cache = StreamlitForecastCache()
        compute = MagicMock(return_value="result_value")
        result = cache.get_or_compute(key="k", ttl=60, compute=compute)
        assert result == "result_value"
        compute.assert_called_once()

    def test_get_or_compute_calls_compute_every_time(self):
        """StreamlitForecastCache does not cache — it delegates to st.cache_data."""
        cache = StreamlitForecastCache()
        compute = MagicMock(return_value=42)
        cache.get_or_compute(key="k", ttl=60, compute=compute)
        cache.get_or_compute(key="k", ttl=60, compute=compute)
        assert compute.call_count == 2


# ---------------------------------------------------------------------------
# TTLForecastCache — hit / miss / expiry
# ---------------------------------------------------------------------------

class TestTTLForecastCache:
    def test_protocol_compliant(self):
        cache = TTLForecastCache()
        _assert_protocol_compliant(cache)

    def test_cache_miss_calls_compute(self):
        cache = TTLForecastCache(maxsize=10, ttl=60)
        compute = MagicMock(return_value="value1")
        result = cache.get_or_compute(key="zone-a", ttl=60, compute=compute)
        assert result == "value1"
        compute.assert_called_once()

    def test_cache_hit_skips_compute(self):
        cache = TTLForecastCache(maxsize=10, ttl=60)
        compute = MagicMock(return_value="value1")
        cache.get_or_compute(key="zone-a", ttl=60, compute=compute)
        cache.get_or_compute(key="zone-a", ttl=60, compute=compute)
        compute.assert_called_once()

    def test_different_keys_are_independent(self):
        cache = TTLForecastCache(maxsize=10, ttl=60)
        compute_a = MagicMock(return_value="a")
        compute_b = MagicMock(return_value="b")
        res_a = cache.get_or_compute(key="zone-a", ttl=60, compute=compute_a)
        res_b = cache.get_or_compute(key="zone-b", ttl=60, compute=compute_b)
        assert res_a == "a"
        assert res_b == "b"
        compute_a.assert_called_once()
        compute_b.assert_called_once()

    def test_cache_expiry_triggers_recompute(self):
        """Entries expire after TTL seconds; recompute should be triggered."""
        cache = TTLForecastCache(maxsize=10, ttl=1)  # 1-second TTL
        compute = MagicMock(side_effect=["first", "second"])
        cache.get_or_compute(key="zone-a", ttl=1, compute=compute)
        time.sleep(1.2)  # wait for entry to expire
        result = cache.get_or_compute(key="zone-a", ttl=1, compute=compute)
        assert result == "second"
        assert compute.call_count == 2

    def test_clear_removes_all_entries(self):
        cache = TTLForecastCache(maxsize=10, ttl=60)
        compute = MagicMock(side_effect=["first", "second"])
        cache.get_or_compute(key="zone-a", ttl=60, compute=compute)
        cache.clear()
        cache.get_or_compute(key="zone-a", ttl=60, compute=compute)
        assert compute.call_count == 2

    def test_size_property(self):
        cache = TTLForecastCache(maxsize=10, ttl=60)
        assert cache.size == 0
        cache.get_or_compute(key="zone-a", ttl=60, compute=lambda: "v")
        assert cache.size == 1
        cache.get_or_compute(key="zone-b", ttl=60, compute=lambda: "v")
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0

    def test_thread_safety(self):
        """Concurrent access to the same key must not call compute more than once
        per cache miss (best-effort, non-strict — we verify it doesn't crash)."""
        import threading
        cache = TTLForecastCache(maxsize=10, ttl=60)
        results: list[str] = []
        errors: list[Exception] = []

        def _task(key: str) -> None:
            try:
                val = cache.get_or_compute(key=key, ttl=60, compute=lambda: f"val-{key}")
                results.append(val)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_task, args=(f"zone-{i % 3}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 20


# ---------------------------------------------------------------------------
# make_forecast_cache factory
# ---------------------------------------------------------------------------

class TestMakeForecastCache:
    def test_streamlit_backend(self):
        cache = make_forecast_cache("streamlit")
        assert isinstance(cache, StreamlitForecastCache)

    def test_ttl_backend(self):
        cache = make_forecast_cache("ttl")
        assert isinstance(cache, TTLForecastCache)

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown cache backend"):
            make_forecast_cache("redis")  # type: ignore[arg-type]

    def test_default_backend_is_ttl(self):
        cache = make_forecast_cache()
        assert isinstance(cache, TTLForecastCache)
