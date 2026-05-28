"""Tests for app/domain/warnings.py — synthesize_warnings()."""
from __future__ import annotations

import pandas as pd
import pytest

from app.domain.warnings import synthesize_warnings


def _df(
    *,
    wind_kt: float = 10.0,
    gust_kt: float = 12.0,
    wave_height_m: float | None = 0.5,
    visibility_m: float = 10_000.0,
    hours: int = 24,
    include_timestamp: bool = True,
) -> pd.DataFrame:
    data: dict = {
        "wind_kt": [wind_kt] * hours,
        "gust_kt": [gust_kt] * hours,
        "visibility_m": [visibility_m] * hours,
    }
    if wave_height_m is not None:
        data["wave_height_m"] = [wave_height_m] * hours
    if include_timestamp:
        data["timestamp"] = pd.date_range("2026-05-18", periods=hours, freq="h")
    return pd.DataFrame(data)


class TestNoWarnings:
    def test_calm_conditions_returns_empty(self):
        result = synthesize_warnings(_df(wind_kt=10, gust_kt=14, wave_height_m=0.5))
        assert result == []

    def test_empty_dataframe_returns_empty(self):
        assert synthesize_warnings(pd.DataFrame()) == []

    def test_none_returns_empty(self):
        assert synthesize_warnings(None) == []


class TestWindWarnings:
    def test_strong_wind_by_sustained(self):
        warnings = synthesize_warnings(_df(wind_kt=22, gust_kt=20))
        events = [w["event"] for w in warnings]
        assert "Strong Wind Warning" in events

    def test_strong_wind_by_gust(self):
        warnings = synthesize_warnings(_df(wind_kt=15, gust_kt=28))
        events = [w["event"] for w in warnings]
        assert "Strong Wind Warning" in events

    def test_gale_warning_by_sustained(self):
        warnings = synthesize_warnings(_df(wind_kt=35, gust_kt=38))
        events = [w["event"] for w in warnings]
        assert "Gale Warning" in events
        assert "Strong Wind Warning" not in events

    def test_gale_warning_by_gust(self):
        warnings = synthesize_warnings(_df(wind_kt=25, gust_kt=41))
        events = [w["event"] for w in warnings]
        assert "Gale Warning" in events

    def test_storm_warning(self):
        warnings = synthesize_warnings(_df(wind_kt=50, gust_kt=60))
        events = [w["event"] for w in warnings]
        assert "Storm Warning" in events
        assert "Gale Warning" not in events
        assert "Strong Wind Warning" not in events

    def test_storm_by_gust_only(self):
        warnings = synthesize_warnings(_df(wind_kt=40, gust_kt=56))
        events = [w["event"] for w in warnings]
        assert "Storm Warning" in events

    def test_severity_is_severe_for_gale(self):
        warnings = synthesize_warnings(_df(wind_kt=35, gust_kt=38))
        gale = next(w for w in warnings if w["event"] == "Gale Warning")
        assert gale["severity"] == "Severe"

    def test_severity_is_moderate_for_strong_wind(self):
        warnings = synthesize_warnings(_df(wind_kt=22, gust_kt=20))
        sw = next(w for w in warnings if w["event"] == "Strong Wind Warning")
        assert sw["severity"] == "Moderate"


class TestWaveWarnings:
    def test_rough_sea(self):
        warnings = synthesize_warnings(_df(wave_height_m=2.5))
        events = [w["event"] for w in warnings]
        assert "Rough Sea Warning" in events

    def test_very_rough_sea(self):
        warnings = synthesize_warnings(_df(wave_height_m=4.0))
        events = [w["event"] for w in warnings]
        assert "Very Rough Sea Warning" in events
        assert "Rough Sea Warning" not in events

    def test_no_wave_column_skips_wave_check(self):
        df = _df(wave_height_m=None)
        df["wind_kt"] = 10
        df["gust_kt"] = 12
        result = synthesize_warnings(df)
        assert all("Sea" not in w["event"] for w in result)


class TestFogWarning:
    def test_dense_fog_advisory(self):
        warnings = synthesize_warnings(_df(visibility_m=500))
        events = [w["event"] for w in warnings]
        assert "Dense Fog Advisory" in events

    def test_borderline_no_fog(self):
        warnings = synthesize_warnings(_df(visibility_m=1000))
        events = [w["event"] for w in warnings]
        assert "Dense Fog Advisory" not in events

    def test_fog_severity_is_minor(self):
        warnings = synthesize_warnings(_df(visibility_m=200))
        fog = next(w for w in warnings if w["event"] == "Dense Fog Advisory")
        assert fog["severity"] == "Minor"


class TestMultipleWarnings:
    def test_gale_plus_fog(self):
        warnings = synthesize_warnings(_df(wind_kt=35, gust_kt=38, visibility_m=300))
        events = {w["event"] for w in warnings}
        assert "Gale Warning" in events
        assert "Dense Fog Advisory" in events

    def test_sorted_severe_first(self):
        warnings = synthesize_warnings(_df(wind_kt=35, gust_kt=38, visibility_m=300))
        severities = [w["severity"] for w in warnings]
        order = {"Severe": 0, "Moderate": 1, "Minor": 2, "Unknown": 3}
        assert severities == sorted(severities, key=lambda s: order.get(s, 9))


class TestWarningShape:
    def test_required_keys_present(self):
        warnings = synthesize_warnings(_df(wind_kt=35, gust_kt=38))
        for w in warnings:
            for key in ("event", "severity", "urgency", "headline", "description", "effective", "expires", "status"):
                assert key in w, f"Missing key {key!r}"

    def test_status_is_actual(self):
        warnings = synthesize_warnings(_df(wind_kt=35, gust_kt=38))
        for w in warnings:
            assert w["status"] == "Actual"

    def test_headline_contains_speed(self):
        warnings = synthesize_warnings(_df(wind_kt=35, gust_kt=38))
        gale = next(w for w in warnings if w["event"] == "Gale Warning")
        assert "35" in gale["headline"] or "38" in gale["headline"]


class TestOnlyFirst24Hours:
    def test_warning_beyond_24h_ignored(self):
        # Calm for first 24 hours, gale for hours 25-48
        hours = 48
        wind = [10.0] * 24 + [35.0] * 24
        gust = [12.0] * 24 + [40.0] * 24
        df = pd.DataFrame({
            "wind_kt": wind,
            "gust_kt": gust,
            "visibility_m": [10_000.0] * hours,
            "timestamp": pd.date_range("2026-05-18", periods=hours, freq="h"),
        })
        result = synthesize_warnings(df)
        assert result == []
