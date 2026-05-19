"""Tests for services/forecast_service.py with mocked HTTP."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.domain.profiles import get_default_profile
from app.domain.regions import SailingRegion, SailingZone
from app.services.forecast_service import ForecastOptions, ZoneForecast, _fetch_and_score


def _make_zone() -> SailingZone:
    return SailingZone(
        id="test-zone",
        name="Test Zone",
        latitude=37.808,
        longitude=-122.435,
        exposure="open",
        hazards=["fog"],
    )


def _make_region(zone: SailingZone) -> SailingRegion:
    return SailingRegion(
        id="test-region",
        name="Test Region",
        country="US",
        timezone="America/Los_Angeles",
        tide_station_id=None,
        nws_zone=None,
        zones=[zone],
    )


class TestFetchAndScore:
    def test_returns_zone_forecast(self, open_meteo_fixture):
        mock_session = MagicMock()
        profile = get_default_profile()

        with patch(
            "app.services.forecast_service.fetch_forecast",
            return_value=open_meteo_fixture,
        ):
            zone = _make_zone()
            region = _make_region(zone)
            opts = ForecastOptions(days=1, timezone="America/Los_Angeles")
            result = _fetch_and_score(zone, region, opts, session=mock_session, profile=profile)

        assert isinstance(result, ZoneForecast)
        assert not result.df_hourly.empty
        assert "sailability" in result.df_hourly.columns

    def test_verdict_is_valid(self, open_meteo_fixture):
        profile = get_default_profile()
        with patch(
            "app.services.forecast_service.fetch_forecast",
            return_value=open_meteo_fixture,
        ):
            zone = _make_zone()
            region = _make_region(zone)
            opts = ForecastOptions(days=1)
            result = _fetch_and_score(zone, region, opts, session=None, profile=profile)

        assert result.verdict in ("GO", "MAYBE", "NO-GO")

    def test_current_sailability_range(self, open_meteo_fixture):
        profile = get_default_profile()
        with patch(
            "app.services.forecast_service.fetch_forecast",
            return_value=open_meteo_fixture,
        ):
            zone = _make_zone()
            region = _make_region(zone)
            result = _fetch_and_score(zone, region, ForecastOptions(), session=None, profile=profile)

        assert 0.0 <= result.current_sailability <= 100.0

    def test_best_windows_returned(self, open_meteo_fixture):
        profile = get_default_profile()
        with patch(
            "app.services.forecast_service.fetch_forecast",
            return_value=open_meteo_fixture,
        ):
            zone = _make_zone()
            region = _make_region(zone)
            result = _fetch_and_score(zone, region, ForecastOptions(), session=None, profile=profile)

        assert isinstance(result.best_sail_windows, list)

    def test_profile_stored_on_forecast(self, open_meteo_fixture):
        profile = get_default_profile()
        with patch(
            "app.services.forecast_service.fetch_forecast",
            return_value=open_meteo_fixture,
        ):
            zone = _make_zone()
            region = _make_region(zone)
            result = _fetch_and_score(zone, region, ForecastOptions(), session=None, profile=profile)

        assert result.profile is not None
        assert result.profile.id == profile.id
