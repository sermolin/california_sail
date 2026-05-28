"""Tests for app/ui/zone_filters.py — no Streamlit dependency."""
from __future__ import annotations

import pandas as pd
import pytest

from app.domain.regions import SailingRegion, SailingZone
from app.services.forecast_service import ZoneForecast
from app.ui.zone_filters import apply_top_n, default_zone_index, filter_forecasts


def _make_zone(zone_id: str, name: str) -> SailingZone:
    return SailingZone(
        id=zone_id, name=name,
        latitude=37.8, longitude=-122.4,
        exposure="open", hazards=[],
    )


def _make_region(zone: SailingZone | None = None) -> SailingRegion:
    placeholder = zone or _make_zone("placeholder", "Placeholder")
    return SailingRegion(
        id="test-region", name="Test Region",
        country="US", timezone="America/Los_Angeles",
        tide_station_id=None, nws_zone=None,
        zones=[placeholder],
    )


def _make_forecast(zone_id: str, name: str, score: float = 70.0) -> ZoneForecast:
    zone = _make_zone(zone_id, name)
    region = _make_region()
    ts = pd.date_range("2026-05-15", periods=24, freq="h")
    df = pd.DataFrame({
        "timestamp": ts,
        "wind_kt": [12.0] * 24,
        "gust_kt": [15.0] * 24,
        "wind_dir_deg": [270.0] * 24,
        "visibility_m": [10000.0] * 24,
        "wind_score": [80.0] * 24,
        "sea_score": [50.0] * 24,
        "visibility_score": [100.0] * 24,
        "gates_passed": [True] * 24,
        "wat_penalty": [0.0] * 24,
        "sailability": [score] * 24,
    })
    return ZoneForecast(
        zone=zone, region=region,
        df_hourly=df,
        df_daily=pd.DataFrame({"date": ts[:1], "sailability_avg": [score]}),
        best_sail_windows=[],
        current_sailability=score,
        verdict="GO" if score >= 65 else "MAYBE",
        has_marine_data=False,
        has_tide_data=False,
    )


_RESULTS = [
    _make_forecast("costa-smeralda", "Costa Smeralda", 85.0),
    _make_forecast("gulf-orosei", "Gulf of Orosei / Cala Gonone", 72.0),
    _make_forecast("alghero", "Alghero", 55.0),
    _make_forecast("cagliari", "Cagliari Gulf", 40.0),
]


class TestFilterForecasts:
    def test_empty_query_returns_all(self):
        assert filter_forecasts(_RESULTS, "") == _RESULTS

    def test_whitespace_query_returns_all(self):
        assert filter_forecasts(_RESULTS, "   ") == _RESULTS

    def test_matches_zone_name(self):
        result = filter_forecasts(_RESULTS, "Alghero")
        assert len(result) == 1
        assert result[0].zone.id == "alghero"

    def test_case_insensitive(self):
        result = filter_forecasts(_RESULTS, "GONONE")
        assert len(result) == 1
        assert result[0].zone.id == "gulf-orosei"

    def test_matches_zone_id(self):
        result = filter_forecasts(_RESULTS, "cagliari")
        assert len(result) == 1
        assert result[0].zone.id == "cagliari"

    def test_no_match_returns_empty(self):
        assert filter_forecasts(_RESULTS, "zzznomatch") == []

    def test_partial_match_on_name(self):
        # "gulf" appears in both "Gulf of Orosei / Cala Gonone" and "Cagliari Gulf"
        result = filter_forecasts(_RESULTS, "gulf")
        ids = {r.zone.id for r in result}
        assert ids == {"gulf-orosei", "cagliari"}

    def test_empty_input_list(self):
        assert filter_forecasts([], "alghero") == []


class TestApplyTopN:
    def test_top_3_of_4(self):
        result = apply_top_n(_RESULTS, 3)
        assert len(result) == 3
        assert result == _RESULTS[:3]

    def test_n_larger_than_list(self):
        result = apply_top_n(_RESULTS, 10)
        assert result == _RESULTS

    def test_n_none_returns_all(self):
        assert apply_top_n(_RESULTS, None) == _RESULTS

    def test_n_zero_returns_all(self):
        assert apply_top_n(_RESULTS, 0) == _RESULTS

    def test_n_negative_returns_all(self):
        assert apply_top_n(_RESULTS, -1) == _RESULTS

    def test_empty_list(self):
        assert apply_top_n([], 5) == []


class TestDefaultZoneIndex:
    def test_found_returns_correct_index(self):
        assert default_zone_index(_RESULTS, "alghero") == 2

    def test_not_found_returns_zero(self):
        assert default_zone_index(_RESULTS, "nonexistent") == 0

    def test_none_favorite_returns_zero(self):
        assert default_zone_index(_RESULTS, None) == 0

    def test_empty_results_returns_zero(self):
        assert default_zone_index([], "alghero") == 0

    def test_first_item_returns_zero(self):
        assert default_zone_index(_RESULTS, "costa-smeralda") == 0
