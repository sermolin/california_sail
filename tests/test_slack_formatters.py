"""Tests for app/bot/slack_formatters.py.

Verifies that each formatter produces non-empty mrkdwn strings with key
content present, and that Slack-specific formatting (no backslash escaping,
correct bold syntax) is used correctly.
"""
from __future__ import annotations

import pytest

from app.bot.slack_formatters import (
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
# Shared fixtures (same shape as app/mcp/tools.py returns)
# ---------------------------------------------------------------------------

_REGIONS = [
    {"id": "sf-bay", "name": "San Francisco Bay", "country": "US", "n_zones": 8},
    {"id": "sardinia", "name": "Sardinia", "country": "IT", "n_zones": 9},
]

_ZONES = [
    {
        "id": "city-front", "name": "City Front",
        "latitude": 37.808, "longitude": -122.435,
        "exposure": "open", "hazards": ["fog", "shipping traffic"],
        "flood_dir_deg": 55.0,
    },
]

_PROFILES = [
    {
        "id": "cruiser", "name": "Cruiser", "emoji": "⛵",
        "boat_size_hint": "30–45 ft", "ideal_wind_kt": [10.0, 18.0],
        "max_gust_kt": 30.0, "max_wave_m": 2.5, "min_visibility_km": 1.0,
        "requires_low_chop": False, "chop_penalty": 25.0,
        "chop_period_s": 4.0, "wat_min_current_kt": 1.0,
    },
]

_FORECAST = {
    "zone": {"id": "city-front", "name": "City Front"},
    "region": {"id": "sf-bay", "name": "San Francisco Bay"},
    "profile": {"id": "cruiser", "name": "Cruiser"},
    "current_sailability": 72.5,
    "verdict": "GO",
    "has_marine_data": True,
    "has_tide_data": False,
    "best_sail_windows": [
        {"start": "2026-05-15T10:00:00", "end": "2026-05-15T12:00:00", "score": 78.0},
    ],
    "daily": [
        {"date": "2026-05-15", "sailability_avg": 70.0, "wind_kt_avg": 15.0,
         "gust_kt_max": 22.0, "wave_height_m_avg": 1.2},
    ],
    "warnings": [],
}

_RANKED = [
    {
        "rank": 1, "zone_id": "city-front", "zone_name": "City Front",
        "sailability": 72.5, "verdict": "GO",
        "avg_wind_kt": 15.0, "max_gust_kt": 22.0,
        "avg_wave_m": 1.2, "has_warnings": False,
    },
    {
        "rank": 2, "zone_id": "south-bay", "zone_name": "South Bay",
        "sailability": 25.0, "verdict": "NO-GO",
        "avg_wind_kt": 38.0, "max_gust_kt": 55.0,
        "avg_wave_m": 3.5, "has_warnings": True,
    },
]

_WINDOWS = [
    {"start": "2026-05-15T10:00:00", "end": "2026-05-15T12:00:00",
     "score": 78.0, "verdict": "GO"},
    {"start": "2026-05-15T14:00:00", "end": "2026-05-15T16:00:00",
     "score": 65.0, "verdict": "GO"},
]

_WARNINGS = [
    {
        "event": "Gale Warning", "severity": "Moderate",
        "headline": "Gale Warning issued May 15 until May 17",
        "expires": "2026-05-17T21:00:00-07:00",
    },
]

_EXPLAIN = {
    "hour": "2026-05-15T12:00:00",
    "sailability": 72.5,
    "verdict": "GO",
    "wind_score": 80.0,
    "sea_score": 70.0,
    "visibility_score": 95.0,
    "gates_passed": True,
    "wat_penalty": 5.0,
    "why_string": "Good sailing conditions with moderate westerly wind.",
    "profile_thresholds": {
        "ideal_wind_kt": [10.0, 18.0],
        "max_gust_kt": 30.0,
        "max_wave_m": 2.5,
    },
}


# ---------------------------------------------------------------------------
# format_regions
# ---------------------------------------------------------------------------

class TestFormatRegions:
    def test_returns_string(self):
        assert isinstance(format_regions(_REGIONS), str)

    def test_contains_region_names(self):
        out = format_regions(_REGIONS)
        assert "San Francisco Bay" in out
        assert "Sardinia" in out

    def test_contains_compare_hint(self):
        assert "/compare" in format_regions(_REGIONS)

    def test_empty_list(self):
        assert "No regions found" in format_regions([])

    def test_no_backslash_escaping(self):
        out = format_regions(_REGIONS)
        assert r"\(" not in out and r"\)" not in out

    def test_bold_header(self):
        assert "*Sailing regions:*" in format_regions(_REGIONS)


# ---------------------------------------------------------------------------
# format_zones
# ---------------------------------------------------------------------------

class TestFormatZones:
    def test_returns_string(self):
        assert isinstance(format_zones(_ZONES, "sf-bay"), str)

    def test_contains_zone_name(self):
        assert "City Front" in format_zones(_ZONES, "sf-bay")

    def test_contains_hazards(self):
        out = format_zones(_ZONES, "sf-bay")
        assert "fog" in out

    def test_contains_forecast_hint(self):
        assert "/forecast" in format_zones(_ZONES, "sf-bay")

    def test_empty_list(self):
        assert "No zones found" in format_zones([], "sf-bay")


# ---------------------------------------------------------------------------
# format_profiles
# ---------------------------------------------------------------------------

class TestFormatProfiles:
    def test_returns_string(self):
        assert isinstance(format_profiles(_PROFILES), str)

    def test_contains_profile_name(self):
        assert "Cruiser" in format_profiles(_PROFILES)

    def test_contains_wind_range(self):
        assert "10" in format_profiles(_PROFILES)
        assert "18" in format_profiles(_PROFILES)

    def test_empty_list(self):
        assert "No profiles found" in format_profiles([])


# ---------------------------------------------------------------------------
# format_forecast
# ---------------------------------------------------------------------------

class TestFormatForecast:
    def test_returns_string(self):
        assert isinstance(format_forecast(_FORECAST), str)

    def test_contains_zone_name(self):
        assert "City Front" in format_forecast(_FORECAST)

    def test_contains_verdict(self):
        assert "GO" in format_forecast(_FORECAST)

    def test_contains_score(self):
        assert "72" in format_forecast(_FORECAST)

    def test_contains_windows(self):
        assert "Best sailing windows" in format_forecast(_FORECAST)

    def test_no_active_warnings_not_shown(self):
        out = format_forecast(_FORECAST)
        assert "Active warnings" not in out

    def test_warnings_shown_when_present(self):
        fc = {**_FORECAST, "warnings": _WARNINGS}
        assert "Gale Warning" in format_forecast(fc)


# ---------------------------------------------------------------------------
# format_compare
# ---------------------------------------------------------------------------

class TestFormatCompare:
    def test_returns_string(self):
        assert isinstance(format_compare(_RANKED, "sf-bay"), str)

    def test_contains_all_zones(self):
        out = format_compare(_RANKED, "sf-bay")
        assert "City Front" in out
        assert "South Bay" in out

    def test_warning_flag_shown(self):
        out = format_compare(_RANKED, "sf-bay")
        assert "⚠️" in out

    def test_empty_list(self):
        assert "No zones found" in format_compare([], "sf-bay")

    def test_no_backslash_escaping(self):
        out = format_compare(_RANKED, "sf-bay")
        assert r"\." not in out


# ---------------------------------------------------------------------------
# format_windows
# ---------------------------------------------------------------------------

class TestFormatWindows:
    def test_returns_string(self):
        assert isinstance(format_windows(_WINDOWS, "city-front"), str)

    def test_contains_zone_id(self):
        assert "city-front" in format_windows(_WINDOWS, "city-front")

    def test_contains_scores(self):
        out = format_windows(_WINDOWS, "city-front")
        assert "78" in out

    def test_empty_list(self):
        assert "No good windows found" in format_windows([], "city-front")


# ---------------------------------------------------------------------------
# format_warnings
# ---------------------------------------------------------------------------

class TestFormatWarnings:
    def test_no_warnings(self):
        out = format_warnings([], "sf-bay")
        assert "No active marine warnings" in out
        assert "✅" in out

    def test_returns_string(self):
        assert isinstance(format_warnings(_WARNINGS, "sf-bay"), str)

    def test_contains_event_name(self):
        assert "Gale Warning" in format_warnings(_WARNINGS, "sf-bay")

    def test_contains_headline(self):
        assert "May 15" in format_warnings(_WARNINGS, "sf-bay")

    def test_contains_severity_emoji(self):
        out = format_warnings(_WARNINGS, "sf-bay")
        assert "🟠" in out  # Moderate


# ---------------------------------------------------------------------------
# format_explain
# ---------------------------------------------------------------------------

class TestFormatExplain:
    def test_returns_string(self):
        assert isinstance(format_explain(_EXPLAIN, "city-front"), str)

    def test_contains_zone_id(self):
        assert "city-front" in format_explain(_EXPLAIN, "city-front")

    def test_contains_components(self):
        out = format_explain(_EXPLAIN, "city-front")
        assert "Wind score" in out
        assert "Sea score" in out
        assert "Visibility score" in out

    def test_gates_passed_shown(self):
        assert "✅" in format_explain(_EXPLAIN, "city-front")

    def test_gates_failed_shown(self):
        ex = {**_EXPLAIN, "gates_passed": False}
        assert "❌" in format_explain(ex, "city-front")

    def test_contains_why_string(self):
        assert "moderate westerly wind" in format_explain(_EXPLAIN, "city-front")

    def test_contains_thresholds(self):
        out = format_explain(_EXPLAIN, "city-front")
        assert "Ideal wind" in out
