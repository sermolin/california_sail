"""Tests for region_service.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.domain.regions import SailingRegion, SailingZone
from app.services.forecast_service import ZoneForecast
from app.services.region_service import get_all_zone_forecasts, get_region_by_name


def _make_region(n_zones: int = 2) -> SailingRegion:
    zones = [
        SailingZone(
            id=f"zone-{i}", name=f"Zone {i}",
            latitude=37.8 + i * 0.01, longitude=-122.4 + i * 0.01,
            exposure="open", hazards=[],
        )
        for i in range(n_zones)
    ]
    return SailingRegion(
        id="test-region", name="Test Region",
        country="US", timezone="America/Los_Angeles",
        tide_station_id="9414290", nws_zone="PZZ545",
        zones=zones,
    )


def _make_zone_forecast(zone: SailingZone, region: SailingRegion, score: float = 70.0) -> ZoneForecast:
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


class TestGetAllZoneForecasts:
    def test_returns_list_sorted_best_first(self):
        region = _make_region(n_zones=3)

        scores = [40.0, 80.0, 60.0]  # zone 0, 1, 2
        side_effects = [
            _make_zone_forecast(region.zones[i], region, score=scores[i])
            for i in range(3)
        ]

        with patch("app.services.region_service.get_zone_forecast", side_effect=side_effects):
            results = get_all_zone_forecasts(region, days=3)

        assert len(results) == 3
        sails = [r.current_sailability for r in results]
        assert sails == sorted(sails, reverse=True)

    def test_failed_zone_is_skipped(self):
        region = _make_region(n_zones=2)

        def fake_forecast(**kwargs):
            if kwargs["zone_id"] == "zone-0":
                raise RuntimeError("API error")
            return _make_zone_forecast(region.zones[1], region, score=70.0)

        with patch("app.services.region_service.get_zone_forecast", side_effect=fake_forecast):
            results = get_all_zone_forecasts(region, days=3)

        assert len(results) == 1
        assert results[0].zone.id == "zone-1"

    def test_on_progress_called_for_every_zone(self):
        region = _make_region(n_zones=3)
        side_effects = [
            _make_zone_forecast(region.zones[i], region, score=float(i * 10 + 50))
            for i in range(3)
        ]

        calls: list[tuple[int, int, str]] = []

        def on_progress(done: int, total: int, zone_id: str) -> None:
            calls.append((done, total, zone_id))

        with patch("app.services.region_service.get_zone_forecast", side_effect=side_effects):
            get_all_zone_forecasts(region, days=3, on_progress=on_progress)

        assert len(calls) == 3
        # final call must have done == total == 3
        final_done, final_total, _ = calls[-1]
        assert final_done == final_total == 3

    def test_on_progress_none_does_not_raise(self):
        region = _make_region(n_zones=2)
        side_effects = [
            _make_zone_forecast(region.zones[i], region, score=70.0)
            for i in range(2)
        ]
        with patch("app.services.region_service.get_zone_forecast", side_effect=side_effects):
            results = get_all_zone_forecasts(region, days=3, on_progress=None)
        assert len(results) == 2


class TestGetRegionByName:
    def test_exact_match(self):
        region = _make_region()
        region_list = [region]
        found = get_region_by_name(region_list, "Test Region")
        assert found is region

    def test_case_insensitive(self):
        region = _make_region()
        found = get_region_by_name([region], "test region")
        assert found is region

    def test_not_found_returns_none(self):
        region = _make_region()
        result = get_region_by_name([region], "Nonexistent")
        assert result is None
