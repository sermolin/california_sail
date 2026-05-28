"""Tests for app/mcp/tools.py — all 8 tool functions with mocked services."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.domain.profiles import get_default_profile, get_all_profiles
from app.domain.regions import SailingRegion, SailingZone
from app.mcp.serializers import profile_to_dict
from app.services.forecast_service import ZoneForecast

# Tools module — import the functions directly (no server runtime needed)
import app.mcp.tools as tools


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_regions_cache():
    """Reset module-level region cache between tests."""
    original = tools._regions
    tools._regions = None
    yield
    tools._regions = original


def _make_zone(zone_id: str = "city-front") -> SailingZone:
    return SailingZone(
        id=zone_id,
        name="City Front",
        latitude=37.808,
        longitude=-122.435,
        exposure="open",
        hazards=["shipping traffic"],
        flood_dir_deg=55.0,
    )


def _make_region(zone_id: str = "city-front") -> SailingRegion:
    zone = _make_zone(zone_id)
    return SailingRegion(
        id="sf-bay",
        name="San Francisco Bay",
        country="US",
        timezone="America/Los_Angeles",
        tide_station_id="9414290",
        nws_zone="PZZ545",
        zones=[zone],
    )


def _make_hourly_df(n: int = 48) -> pd.DataFrame:
    times = pd.date_range("2026-05-15", periods=n, freq="h")
    df = pd.DataFrame({
        "wind_kt": [14.0] * n,
        "gust_kt": [20.0] * n,
        "wind_dir_deg": [270.0] * n,
        "wave_height_m": [0.8] * n,
        "wave_period_s": [6.0] * n,
        "tide_height_m": [1.0] * n,
        "visibility_m": [10000.0] * n,
        "sailability": [75.0] * n,
        "wind_score": [80.0] * n,
        "sea_score": [70.0] * n,
        "visibility_score": [100.0] * n,
        "gates_passed": [True] * n,
        "wat_penalty": [0.0] * n,
    }, index=times)
    return df


def _make_daily_df() -> pd.DataFrame:
    dates = pd.date_range("2026-05-15", periods=3, freq="D")
    return pd.DataFrame({
        "sailability": [75.0, 60.0, 80.0],
        "wind_kt": [14.0, 10.0, 16.0],
        "gust_kt": [20.0, 15.0, 22.0],
        "wave_height_m": [0.8, 1.0, 0.6],
    }, index=dates)


def _make_zone_forecast(zone_id: str = "city-front") -> ZoneForecast:
    region = _make_region(zone_id)
    zone = region.zones[0]
    return ZoneForecast(
        zone=zone,
        region=region,
        df_hourly=_make_hourly_df(),
        df_daily=_make_daily_df(),
        best_sail_windows=[
            (pd.Timestamp("2026-05-15T14:00"), pd.Timestamp("2026-05-15T17:00"), 82.4),
        ],
        current_sailability=75.0,
        verdict="Good sailing",
        has_marine_data=True,
        has_tide_data=True,
        warnings=[],
        profile=get_default_profile(),
    )


def _make_regions_list() -> list[SailingRegion]:
    return [_make_region()]


# ---------------------------------------------------------------------------
# 1. list_regions
# ---------------------------------------------------------------------------

class TestListRegions:
    def test_returns_list(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            result = tools.list_regions()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_entry_has_required_keys(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            result = tools.list_regions()
        entry = result[0]
        assert entry["id"] == "sf-bay"
        assert entry["name"] == "San Francisco Bay"
        assert entry["country"] == "US"
        assert entry["n_zones"] == 1


# ---------------------------------------------------------------------------
# 2. list_zones
# ---------------------------------------------------------------------------

class TestListZones:
    def test_returns_zones_for_valid_region(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            result = tools.list_zones("sf-bay")
        assert isinstance(result, list)
        assert result[0]["id"] == "city-front"

    def test_raises_for_unknown_region(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with pytest.raises(ValueError, match="Unknown region_id"):
                tools.list_zones("nonexistent-region")

    def test_zone_entry_has_coordinates(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            result = tools.list_zones("sf-bay")
        assert "latitude" in result[0]
        assert "longitude" in result[0]


# ---------------------------------------------------------------------------
# 3. list_profiles
# ---------------------------------------------------------------------------

class TestListProfiles:
    def test_returns_list(self):
        result = tools.list_profiles()
        assert isinstance(result, list)
        assert len(result) >= 3  # school, cruiser, racer

    def test_cruiser_present(self):
        result = tools.list_profiles()
        ids = [p["id"] for p in result]
        assert "cruiser" in ids

    def test_profile_entry_has_thresholds(self):
        result = tools.list_profiles()
        cruiser = next(p for p in result if p["id"] == "cruiser")
        assert "ideal_wind_kt" in cruiser
        assert "max_gust_kt" in cruiser
        assert "max_wave_m" in cruiser


# ---------------------------------------------------------------------------
# 4. get_zone_forecast
# ---------------------------------------------------------------------------

class TestGetZoneForecast:
    def test_returns_dict_with_verdict(self):
        fc = _make_zone_forecast()
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch("app.mcp.tools._svc_get_zone_forecast", return_value=fc):
                result = tools.get_zone_forecast("city-front")
        assert "verdict" in result
        assert "current_sailability" in result

    def test_summary_has_no_hourly(self):
        fc = _make_zone_forecast()
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch("app.mcp.tools._svc_get_zone_forecast", return_value=fc):
                result = tools.get_zone_forecast("city-front", summary=True)
        assert "hourly" not in result

    def test_full_has_hourly(self):
        fc = _make_zone_forecast()
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch("app.mcp.tools._svc_get_zone_forecast", return_value=fc):
                result = tools.get_zone_forecast("city-front", summary=False)
        assert "hourly" in result

    def test_raises_for_unknown_zone(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with pytest.raises(ValueError, match="Unknown zone_id"):
                tools.get_zone_forecast("nonexistent-zone")

    def test_days_clamped(self):
        fc = _make_zone_forecast()
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch("app.mcp.tools._svc_get_zone_forecast", return_value=fc) as mock_svc:
                # days=99 should be clamped to 7 before calling service
                tools.get_zone_forecast("city-front", days=99)
                call_kwargs = mock_svc.call_args[1]
                assert call_kwargs["days"] == 7


# ---------------------------------------------------------------------------
# 5. compare_zones_in_region
# ---------------------------------------------------------------------------

class TestCompareZonesInRegion:
    def test_returns_ranked_list(self):
        fc = _make_zone_forecast()
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch("app.mcp.tools.get_all_zone_forecasts", return_value=[fc]):
                result = tools.compare_zones_in_region("sf-bay")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["rank"] == 1

    def test_entry_has_required_keys(self):
        fc = _make_zone_forecast()
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch("app.mcp.tools.get_all_zone_forecasts", return_value=[fc]):
                result = tools.compare_zones_in_region("sf-bay")
        entry = result[0]
        assert "zone_id" in entry
        assert "zone_name" in entry
        assert "sailability" in entry
        assert "verdict" in entry
        assert "has_warnings" in entry

    def test_raises_for_unknown_region(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with pytest.raises(ValueError, match="Unknown region_id"):
                tools.compare_zones_in_region("nonexistent")


# ---------------------------------------------------------------------------
# 6. best_sail_windows
# ---------------------------------------------------------------------------

def _make_forecast_dict(n_windows: int = 1) -> dict:
    """Return a dict matching what tools.get_zone_forecast returns."""
    windows = [
        {"start": f"2026-05-15T1{i}:00:00", "end": f"2026-05-15T1{i+1}:00:00", "score": 80.0 - i * 5}
        for i in range(n_windows)
    ]
    hourly_row = {
        "time": "2026-05-15T14:00:00",
        "wind_kt": 14.0, "gust_kt": 20.0, "wind_dir_deg": 270.0,
        "wave_height_m": 0.8, "wave_period_s": 6.0,
        "visibility_m": 10000.0,
        "sailability": 75.0, "wind_score": 80.0, "sea_score": 70.0,
        "visibility_score": 100.0, "gates_passed": True, "wat_penalty": 0.0,
    }
    profile = profile_to_dict(get_default_profile())
    return {
        "zone": {"id": "city-front", "name": "City Front"},
        "region": {"id": "sf-bay"},
        "profile": profile,
        "current_sailability": 75.0,
        "verdict": "Good sailing",
        "has_marine_data": True,
        "has_tide_data": True,
        "best_sail_windows": windows,
        "daily": [],
        "warnings": [],
        "hourly": [hourly_row] * 48,
    }


class TestBestSailWindows:
    def test_returns_list(self):
        fc_dict = _make_forecast_dict(1)
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch.object(tools, "get_zone_forecast", return_value=fc_dict):
                result = tools.best_sail_windows("city-front")
        assert isinstance(result, list)

    def test_window_entry_has_required_keys(self):
        fc_dict = _make_forecast_dict(1)
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch.object(tools, "get_zone_forecast", return_value=fc_dict):
                result = tools.best_sail_windows("city-front")
        if result:
            w = result[0]
            assert "start" in w
            assert "end" in w
            assert "score" in w
            assert "verdict" in w

    def test_raises_for_unknown_zone(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with pytest.raises(ValueError, match="Unknown zone_id"):
                tools.best_sail_windows("nonexistent-zone")

    def test_top_n_respected(self):
        fc_dict = _make_forecast_dict(n_windows=3)
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch.object(tools, "get_zone_forecast", return_value=fc_dict):
                result = tools.best_sail_windows("city-front", top_n=2)
        assert len(result) <= 2


# ---------------------------------------------------------------------------
# 7. get_active_warnings
# ---------------------------------------------------------------------------

class TestGetActiveWarnings:
    def test_returns_list_for_us_region(self):
        warning = {"event": "SCA", "severity": "Moderate",
                   "headline": "SCA until 8PM", "expires": "..."}
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch.object(tools, "fetch_marine_warnings", return_value=[warning]):
                result = tools.get_active_warnings("sf-bay")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["event"] == "SCA"

    def test_empty_list_when_no_warnings(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch.object(tools, "fetch_marine_warnings", return_value=[]):
                result = tools.get_active_warnings("sf-bay")
        assert result == []

    def test_synthetic_warnings_for_non_us_region(self):
        # Sardinia has no nws_zone — the tool should synthesise from forecast data.
        sardinia_zone = SailingZone(
            id="stintino", name="Stintino", latitude=40.929, longitude=8.227,
            exposure="open", hazards=[],
        )
        sardinia = SailingRegion(
            id="sardinia", name="Sardinia", country="IT",
            timezone="Europe/Rome", tide_station_id=None, nws_zone=None,
            zones=[sardinia_zone],
        )
        calm_df = pd.DataFrame({
            "wind_kt": [10.0] * 24,
            "gust_kt": [12.0] * 24,
            "visibility_m": [10_000.0] * 24,
        })
        with patch.object(tools, "_get_regions", return_value=[sardinia]):
            with patch.object(tools, "fetch_forecast", return_value={}):
                with patch.object(tools, "open_meteo_response_to_df", return_value=calm_df):
                    with patch.object(tools, "marine_response_to_df", return_value=pd.DataFrame()):
                        with patch.object(tools, "fetch_marine_forecast", return_value={}):
                            with patch.object(tools, "merge_to_hourly", return_value=calm_df):
                                result = tools.get_active_warnings("sardinia")
        # Calm conditions → no warnings
        assert isinstance(result, list)
        assert result == []

    def test_synthetic_warning_issued_for_gale(self):
        sardinia_zone = SailingZone(
            id="stintino", name="Stintino", latitude=40.929, longitude=8.227,
            exposure="open", hazards=[],
        )
        sardinia = SailingRegion(
            id="sardinia", name="Sardinia", country="IT",
            timezone="Europe/Rome", tide_station_id=None, nws_zone=None,
            zones=[sardinia_zone],
        )
        gale_df = pd.DataFrame({
            "wind_kt": [35.0] * 24,
            "gust_kt": [42.0] * 24,
            "visibility_m": [10_000.0] * 24,
        })
        with patch.object(tools, "_get_regions", return_value=[sardinia]):
            with patch.object(tools, "fetch_forecast", return_value={}):
                with patch.object(tools, "open_meteo_response_to_df", return_value=gale_df):
                    with patch.object(tools, "marine_response_to_df", return_value=pd.DataFrame()):
                        with patch.object(tools, "fetch_marine_forecast", return_value={}):
                            with patch.object(tools, "merge_to_hourly", return_value=gale_df):
                                result = tools.get_active_warnings("sardinia")
        assert len(result) >= 1
        events = [w["event"] for w in result]
        assert "Gale Warning" in events
        # Each warning must have the four serialised keys
        for w in result:
            for key in ("event", "severity", "headline", "expires"):
                assert key in w

    def test_raises_for_unknown_region(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with pytest.raises(ValueError, match="Unknown region_id"):
                tools.get_active_warnings("nonexistent")


# ---------------------------------------------------------------------------
# 8. explain_score
# ---------------------------------------------------------------------------

class TestExplainScore:
    def test_returns_dict_with_required_keys(self):
        fc_dict = _make_forecast_dict()
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch.object(tools, "get_zone_forecast", return_value=fc_dict):
                result = tools.explain_score("city-front")
        required = ["hour", "sailability", "verdict", "wind_score", "sea_score",
                    "visibility_score", "gates_passed", "wat_penalty",
                    "profile_thresholds", "why_string"]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_why_string_non_empty(self):
        fc_dict = _make_forecast_dict()
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch.object(tools, "get_zone_forecast", return_value=fc_dict):
                result = tools.explain_score("city-front")
        assert isinstance(result["why_string"], str)
        assert len(result["why_string"]) > 0

    def test_hour_offset_clamped(self):
        fc_dict = _make_forecast_dict()
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with patch.object(tools, "get_zone_forecast", return_value=fc_dict):
                # hour_offset=999 should be clamped, not raise
                result = tools.explain_score("city-front", hour_offset=999)
        assert result is not None

    def test_raises_for_unknown_zone(self):
        with patch.object(tools, "_get_regions", return_value=_make_regions_list()):
            with pytest.raises(ValueError, match="Unknown zone_id"):
                tools.explain_score("nonexistent-zone")
