"""Tests for app/mcp/serializers.py."""
import json
import math

import pandas as pd
import pytest

from app.domain.profiles import get_default_profile, get_profile_by_id
from app.domain.regions import SailingRegion, SailingZone
from app.mcp.serializers import (
    _daily_rows,
    _hourly_rows,
    _safe_float,
    _ts_iso,
    profile_to_dict,
    region_to_dict,
    zone_forecast_to_dict,
    zone_to_dict,
)
from app.services.forecast_service import ZoneForecast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zone(zone_id: str = "city-front") -> SailingZone:
    return SailingZone(
        id=zone_id,
        name="City Front",
        latitude=37.808,
        longitude=-122.435,
        exposure="open",
        hazards=["shipping traffic", "fog"],
        flood_dir_deg=55.0,
    )


def _make_region(zone: SailingZone) -> SailingRegion:
    return SailingRegion(
        id="sf-bay",
        name="San Francisco Bay",
        country="US",
        timezone="America/Los_Angeles",
        tide_station_id="9414290",
        nws_zone="PZZ545",
        zones=[zone],
    )


def _make_hourly_df(n: int = 10) -> pd.DataFrame:
    times = pd.date_range("2026-05-15", periods=n, freq="h")
    df = pd.DataFrame({
        "wind_kt": [12.0] * n,
        "gust_kt": [18.0] * n,
        "wind_dir_deg": [270.0] * n,
        "wave_height_m": [0.8] * n,
        "wave_period_s": [6.0] * n,
        "tide_height_m": [1.2] * n,
        "visibility_m": [10000.0] * n,
        "sailability": [75.0] * n,
        "wind_score": [80.0] * n,
        "sea_score": [70.0] * n,
        "visibility_score": [100.0] * n,
        "gates_passed": [True] * n,
        "wat_penalty": [0.0] * n,
    }, index=times)
    return df


def _make_daily_df(n: int = 3) -> pd.DataFrame:
    dates = pd.date_range("2026-05-15", periods=n, freq="D")
    df = pd.DataFrame({
        "sailability": [75.0, 60.0, 80.0][:n],
        "wind_kt": [12.0, 10.0, 15.0][:n],
        "gust_kt": [18.0, 15.0, 22.0][:n],
        "wave_height_m": [0.8, 1.0, 0.5][:n],
    }, index=dates)
    return df


def _make_zone_forecast(summary: bool = True) -> ZoneForecast:
    zone = _make_zone()
    region = _make_region(zone)
    df_hourly = _make_hourly_df(80)
    df_daily = _make_daily_df()
    return ZoneForecast(
        zone=zone,
        region=region,
        df_hourly=df_hourly,
        df_daily=df_daily,
        best_sail_windows=[
            (pd.Timestamp("2026-05-15T14:00"), pd.Timestamp("2026-05-15T17:00"), 82.4),
        ],
        current_sailability=75.0,
        verdict="Good sailing",
        has_marine_data=True,
        has_tide_data=True,
        warnings=[{"event": "Small Craft Advisory", "severity": "Moderate",
                   "headline": "SCA until 8PM", "expires": "2026-05-15T20:00:00"}],
        profile=get_default_profile(),
    )


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_rounds_to_ndigits(self):
        assert _safe_float(3.14159, 2) == 3.14

    def test_nan_returns_none(self):
        assert _safe_float(float("nan")) is None

    def test_inf_returns_none(self):
        assert _safe_float(float("inf")) is None

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_integer_input(self):
        assert _safe_float(42, 2) == 42.0

    def test_string_number(self):
        assert _safe_float("3.5", 1) == 3.5

    def test_non_numeric_string_returns_none(self):
        assert _safe_float("abc") is None


# ---------------------------------------------------------------------------
# _ts_iso
# ---------------------------------------------------------------------------

class TestTsIso:
    def test_pandas_timestamp(self):
        ts = pd.Timestamp("2026-05-15T14:00:00")
        result = _ts_iso(ts)
        assert "2026-05-15" in result
        assert "14:00:00" in result

    def test_none_returns_none(self):
        assert _ts_iso(None) is None


# ---------------------------------------------------------------------------
# zone_to_dict
# ---------------------------------------------------------------------------

class TestZoneToDict:
    def test_required_fields(self):
        zone = _make_zone()
        d = zone_to_dict(zone)
        assert d["id"] == "city-front"
        assert d["name"] == "City Front"
        assert d["exposure"] == "open"
        assert isinstance(d["hazards"], list)
        assert len(d["hazards"]) == 2

    def test_flood_dir_serialized(self):
        zone = _make_zone()
        d = zone_to_dict(zone)
        assert d["flood_dir_deg"] == 55.0

    def test_json_safe(self):
        zone = _make_zone()
        json.dumps(zone_to_dict(zone))  # must not raise


# ---------------------------------------------------------------------------
# region_to_dict
# ---------------------------------------------------------------------------

class TestRegionToDict:
    def test_includes_zones_by_default(self):
        zone = _make_zone()
        region = _make_region(zone)
        d = region_to_dict(region)
        assert "zones" in d
        assert len(d["zones"]) == 1

    def test_excludes_zones_when_requested(self):
        zone = _make_zone()
        region = _make_region(zone)
        d = region_to_dict(region, include_zones=False)
        assert "zones" not in d
        assert d["n_zones"] == 1


# ---------------------------------------------------------------------------
# profile_to_dict
# ---------------------------------------------------------------------------

class TestProfileToDict:
    def test_required_fields(self):
        profile = get_default_profile()
        d = profile_to_dict(profile)
        assert d["id"] == "cruiser"
        assert isinstance(d["ideal_wind_kt"], list)
        assert len(d["ideal_wind_kt"]) == 2

    def test_json_safe(self):
        profile = get_default_profile()
        json.dumps(profile_to_dict(profile))  # must not raise


# ---------------------------------------------------------------------------
# _hourly_rows
# ---------------------------------------------------------------------------

class TestHourlyRows:
    def test_cap_respected(self):
        df = _make_hourly_df(80)
        rows = _hourly_rows(df, cap=10)
        assert len(rows) == 10

    def test_cap_default(self):
        df = _make_hourly_df(100)
        rows = _hourly_rows(df)
        assert len(rows) == 72

    def test_row_structure(self):
        df = _make_hourly_df(5)
        rows = _hourly_rows(df)
        assert "time" in rows[0]
        assert "wind_kt" in rows[0]
        assert "sailability" in rows[0]
        assert "gates_passed" in rows[0]

    def test_json_safe(self):
        df = _make_hourly_df(5)
        rows = _hourly_rows(df)
        json.dumps(rows)  # must not raise

    def test_nan_values_become_none(self):
        import math as _math
        df = _make_hourly_df(3)
        df.loc[:, "wave_height_m"] = float("nan")
        rows = _hourly_rows(df, cap=3)
        for row in rows:
            assert row.get("wave_height_m") is None


# ---------------------------------------------------------------------------
# _daily_rows
# ---------------------------------------------------------------------------

class TestDailyRows:
    def test_structure(self):
        df = _make_daily_df(3)
        rows = _daily_rows(df)
        assert len(rows) == 3
        assert "date" in rows[0]
        assert "sailability_avg" in rows[0]

    def test_json_safe(self):
        df = _make_daily_df(3)
        json.dumps(_daily_rows(df))


# ---------------------------------------------------------------------------
# zone_forecast_to_dict — summary vs full
# ---------------------------------------------------------------------------

class TestZoneForecastToDict:
    def test_summary_has_no_hourly(self):
        fc = _make_zone_forecast()
        d = zone_forecast_to_dict(fc, summary=True)
        assert "hourly" not in d

    def test_full_has_hourly(self):
        fc = _make_zone_forecast()
        d = zone_forecast_to_dict(fc, summary=False)
        assert "hourly" in d

    def test_hourly_cap_respected(self):
        fc = _make_zone_forecast()
        d = zone_forecast_to_dict(fc, summary=False, hourly_cap=10)
        assert len(d["hourly"]) == 10

    def test_required_keys(self):
        fc = _make_zone_forecast()
        d = zone_forecast_to_dict(fc, summary=True)
        for key in ("zone", "region", "profile", "current_sailability", "verdict",
                    "has_marine_data", "has_tide_data", "best_sail_windows", "daily", "warnings"):
            assert key in d, f"Missing key: {key}"

    def test_json_safe_summary(self):
        fc = _make_zone_forecast()
        json.dumps(zone_forecast_to_dict(fc, summary=True))

    def test_json_safe_full(self):
        fc = _make_zone_forecast()
        json.dumps(zone_forecast_to_dict(fc, summary=False))

    def test_warnings_serialized(self):
        fc = _make_zone_forecast()
        d = zone_forecast_to_dict(fc, summary=True)
        assert len(d["warnings"]) == 1
        w = d["warnings"][0]
        assert w["event"] == "Small Craft Advisory"
        assert w["severity"] == "Moderate"

    def test_best_sail_windows_serialized(self):
        fc = _make_zone_forecast()
        d = zone_forecast_to_dict(fc, summary=True)
        assert len(d["best_sail_windows"]) == 1
        win = d["best_sail_windows"][0]
        assert "start" in win
        assert "end" in win
        assert "score" in win
