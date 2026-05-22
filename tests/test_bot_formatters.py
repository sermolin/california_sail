"""Smoke tests for app/bot/formatters.py."""
from __future__ import annotations

import pytest

from app.bot.formatters import (
    format_compare,
    format_explain,
    format_forecast,
    format_profiles,
    format_regions,
    format_warnings,
    format_windows,
    format_zones,
)


# ---------------------------------------------------------------------------
# Fixture dicts (minimal, matching the shape returned by app/mcp/tools.py)
# ---------------------------------------------------------------------------

_REGIONS = [
    {"id": "sf-bay", "name": "San Francisco Bay", "country": "US", "n_zones": 4},
    {"id": "sardinia", "name": "Sardinia", "country": "IT", "n_zones": 3},
]

_ZONES = [
    {"id": "city-front", "name": "City Front", "latitude": 37.808,
     "longitude": -122.435, "exposure": "open", "hazards": ["fog", "shipping"],
     "flood_dir_deg": 55.0},
]

_PROFILES = [
    {"id": "cruiser", "name": "Cruiser", "emoji": "⛵",
     "boat_size_hint": "28–45 ft", "ideal_wind_kt": [10.0, 18.0],
     "max_gust_kt": 30.0, "max_wave_m": 2.5, "min_visibility_km": 1.0,
     "requires_low_chop": False, "chop_penalty": 25.0,
     "chop_period_s": 4.0, "wat_min_current_kt": 1.0},
]

_FORECAST = {
    "zone": {"id": "city-front", "name": "City Front"},
    "region": {"id": "sf-bay", "name": "San Francisco Bay"},
    "profile": {"id": "cruiser", "name": "Cruiser", "ideal_wind_kt": [10.0, 18.0],
                "max_gust_kt": 30.0, "max_wave_m": 2.5},
    "current_sailability": 75.0,
    "verdict": "Good sailing",
    "has_marine_data": True,
    "has_tide_data": True,
    "best_sail_windows": [
        {"start": "2026-05-15T14:00:00", "end": "2026-05-15T17:00:00", "score": 82.0},
    ],
    "daily": [
        {"date": "2026-05-15", "sailability_avg": 75.0, "wind_kt_avg": 14.0,
         "gust_kt_max": 20.0, "wave_height_m_avg": 0.8},
    ],
    "warnings": [],
}

_FORECAST_WITH_WARNINGS = {
    **_FORECAST,
    "warnings": [
        {"event": "Small Craft Advisory", "severity": "Moderate",
         "headline": "SCA until 8PM", "expires": "2026-05-15T20:00:00"},
    ],
}

_COMPARE = [
    {"rank": 1, "zone_id": "city-front", "zone_name": "City Front",
     "sailability": 78.0, "verdict": "Good sailing",
     "avg_wind_kt": 14.0, "max_gust_kt": 20.0, "avg_wave_m": 0.8,
     "has_warnings": False},
    {"rank": 2, "zone_id": "berkeley-oc", "zone_name": "Berkeley OC",
     "sailability": 45.0, "verdict": "Marginal",
     "avg_wind_kt": 8.0, "max_gust_kt": 15.0, "avg_wave_m": 1.2,
     "has_warnings": True},
]

_WINDOWS = [
    {"start": "2026-05-15T14:00:00", "end": "2026-05-15T17:00:00",
     "score": 82.0, "verdict": "Great sailing!"},
    {"start": "2026-05-16T13:00:00", "end": "2026-05-16T16:00:00",
     "score": 70.0, "verdict": "Good sailing"},
]

_WARNINGS_LIST = [
    {"event": "Small Craft Advisory", "severity": "Moderate",
     "headline": "SCA until 8PM PDT", "expires": "2026-05-15T20:00:00-07:00"},
]

_EXPLAIN = {
    "hour": "2026-05-15T14:00:00",
    "sailability": 75.0,
    "verdict": "Good sailing",
    "wind_score": 82.0,
    "sea_score": 70.0,
    "visibility_score": 100.0,
    "gates_passed": True,
    "wat_penalty": 0.0,
    "profile_thresholds": {
        "ideal_wind_kt": [10.0, 18.0],
        "max_gust_kt": 30.0,
        "max_wave_m": 2.5,
        "min_visibility_km": 1.0,
    },
    "why_string": "Wind 14 kt (ideal range), wave 0.8 m (manageable), visibility clear.",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFormatRegions:
    def test_returns_string(self):
        assert isinstance(format_regions(_REGIONS), str)

    def test_contains_region_name(self):
        result = format_regions(_REGIONS)
        assert "San Francisco Bay" in result

    def test_empty_list(self):
        result = format_regions([])
        assert isinstance(result, str)
        assert len(result) > 0


class TestFormatZones:
    def test_returns_string(self):
        assert isinstance(format_zones(_ZONES, "sf-bay"), str)

    def test_contains_zone_name(self):
        result = format_zones(_ZONES, "sf-bay")
        assert "City Front" in result

    def test_contains_zone_id(self):
        result = format_zones(_ZONES, "sf-bay")
        # hyphens are escaped in MarkdownV2
        assert "city" in result and "front" in result


class TestFormatProfiles:
    def test_returns_string(self):
        assert isinstance(format_profiles(_PROFILES), str)

    def test_contains_profile_name(self):
        result = format_profiles(_PROFILES)
        assert "Cruiser" in result

    def test_contains_wind_range(self):
        result = format_profiles(_PROFILES)
        assert "10" in result
        assert "18" in result


class TestFormatForecast:
    def test_returns_string(self):
        assert isinstance(format_forecast(_FORECAST), str)

    def test_contains_zone_name(self):
        result = format_forecast(_FORECAST)
        assert "City Front" in result

    def test_contains_verdict(self):
        result = format_forecast(_FORECAST)
        assert "Good sailing" in result

    def test_contains_windows(self):
        result = format_forecast(_FORECAST)
        assert "Best sailing" in result

    def test_forecast_with_warnings(self):
        result = format_forecast(_FORECAST_WITH_WARNINGS)
        assert "Small Craft Advisory" in result or "Active warnings" in result


class TestFormatCompare:
    def test_returns_string(self):
        assert isinstance(format_compare(_COMPARE, "sf-bay"), str)

    def test_contains_zone_names(self):
        result = format_compare(_COMPARE, "sf-bay")
        assert "City Front" in result
        assert "Berkeley OC" in result

    def test_contains_warning_flag(self):
        result = format_compare(_COMPARE, "sf-bay")
        assert "⚠️" in result  # zone 2 has warnings

    def test_empty_list(self):
        result = format_compare([], "sf-bay")
        assert isinstance(result, str)


class TestFormatWindows:
    def test_returns_string(self):
        assert isinstance(format_windows(_WINDOWS, "city-front"), str)

    def test_contains_score(self):
        result = format_windows(_WINDOWS, "city-front")
        assert "82" in result

    def test_empty_windows(self):
        result = format_windows([], "city-front")
        assert "No good windows" in result


class TestFormatWarnings:
    def test_active_warnings(self):
        result = format_warnings(_WARNINGS_LIST, "sf-bay")
        assert "Small Craft Advisory" in result

    def test_no_warnings(self):
        result = format_warnings([], "sf-bay")
        assert "No active" in result or "✅" in result


class TestFormatExplain:
    def test_returns_string(self):
        assert isinstance(format_explain(_EXPLAIN, "city-front"), str)

    def test_contains_scores(self):
        result = format_explain(_EXPLAIN, "city-front")
        assert "82" in result  # wind score
        assert "70" in result  # sea score

    def test_contains_verdict(self):
        result = format_explain(_EXPLAIN, "city-front")
        assert "Good sailing" in result

    def test_contains_why_string(self):
        result = format_explain(_EXPLAIN, "city-front")
        assert "ideal range" in result or "manageable" in result

    def test_failed_gates(self):
        bad = {**_EXPLAIN, "gates_passed": False}
        result = format_explain(bad, "city-front")
        assert "failed" in result or "capped" in result
