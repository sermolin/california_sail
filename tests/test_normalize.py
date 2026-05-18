"""Tests for domain/normalize.py — Phase 1 (weather) + Phase 2 (marine + tides)."""
import json
from pathlib import Path

import pandas as pd
import pytest

from app.domain.normalize import (
    marine_response_to_df,
    merge_to_hourly,
    noaa_tides_to_df,
    open_meteo_response_to_df,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestOpenMeteoResponseToDf:
    def test_returns_dataframe_with_required_cols(self, open_meteo_fixture):
        df = open_meteo_response_to_df(open_meteo_fixture)
        for col in ("timestamp", "wind_kt", "gust_kt", "wind_dir_deg", "temp_c", "precip_mm", "cloud_pct", "visibility_m"):
            assert col in df.columns, f"Missing column: {col}"

    def test_row_count_matches_time_array(self, open_meteo_fixture):
        df = open_meteo_response_to_df(open_meteo_fixture)
        expected = len(open_meteo_fixture["hourly"]["time"])
        assert len(df) == expected

    def test_wind_converted_from_ms_to_knots(self, open_meteo_fixture):
        df = open_meteo_response_to_df(open_meteo_fixture)
        from app.domain.units import ms_to_knots
        first_ms = open_meteo_fixture["hourly"]["wind_speed_10m"][0]
        assert df["wind_kt"].iloc[0] == pytest.approx(ms_to_knots(first_ms), rel=1e-4)

    def test_empty_hourly_returns_empty_df(self):
        raw = {"hourly": {"time": [], "wind_speed_10m": [], "temperature_2m": []}}
        df = open_meteo_response_to_df(raw)
        assert df.empty

    def test_timestamps_are_datetime(self, open_meteo_fixture):
        df = open_meteo_response_to_df(open_meteo_fixture)
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])

    def test_missing_gust_defaults_to_zero(self):
        raw = {
            "hourly": {
                "time": ["2026-05-15T00:00"],
                "wind_speed_10m": [5.0],
                "temperature_2m": [15.0],
                "wind_direction_10m": [270.0],
                "precipitation": [0.0],
                "cloud_cover": [10.0],
                "visibility": [20000.0],
            }
        }
        df = open_meteo_response_to_df(raw)
        assert df["gust_kt"].iloc[0] == pytest.approx(0.0)


class TestMarineResponseToDf:
    def _fixture(self):
        return json.loads((FIXTURES / "open_meteo_marine_response.json").read_text())

    def test_required_columns_present(self):
        df = marine_response_to_df(self._fixture())
        for col in ("timestamp", "wave_height_m", "wave_period_s", "wave_dir_deg", "swell_height_m", "sea_level_m"):
            assert col in df.columns, f"Missing column: {col}"

    def test_row_count_matches_time(self):
        raw = self._fixture()
        df = marine_response_to_df(raw)
        assert len(df) == len(raw["hourly"]["time"])

    def test_timestamps_are_datetime(self):
        df = marine_response_to_df(self._fixture())
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])

    def test_wave_heights_positive(self):
        df = marine_response_to_df(self._fixture())
        assert (df["wave_height_m"] >= 0.0).all()

    def test_empty_returns_empty_df(self):
        df = marine_response_to_df({"hourly": {"time": []}})
        assert df.empty


class TestNoaaTidesToDf:
    def _fixture(self):
        return json.loads((FIXTURES / "noaa_tides_response.json").read_text())

    def test_required_columns_present(self):
        df = noaa_tides_to_df(self._fixture())
        for col in ("timestamp", "tide_height_m", "tide_rate_m_per_h", "current_speed_kt"):
            assert col in df.columns, f"Missing column: {col}"

    def test_row_count_matches_predictions(self):
        raw = self._fixture()
        df = noaa_tides_to_df(raw)
        assert len(df) == len(raw["predictions"])

    def test_current_speed_non_negative(self):
        df = noaa_tides_to_df(self._fixture())
        assert (df["current_speed_kt"] >= 0.0).all()

    def test_current_speed_bounded(self):
        df = noaa_tides_to_df(self._fixture())
        assert (df["current_speed_kt"] <= 5.0).all()

    def test_rising_tide_positive_rate(self):
        df = noaa_tides_to_df(self._fixture())
        # The fixture has rising heights in the first several rows
        rising_rows = df.head(5)
        # Most rates should be positive (tide rising 0.372 → 1.312)
        assert (rising_rows["tide_rate_m_per_h"].iloc[1:] > 0).all()

    def test_empty_predictions_returns_empty(self):
        df = noaa_tides_to_df({"predictions": []})
        assert df.empty


class TestMergeToHourly:
    def _weather_df(self) -> pd.DataFrame:
        ts = pd.date_range("2026-05-15T00:00", periods=6, freq="h")
        return pd.DataFrame({
            "timestamp": ts,
            "wind_kt": [12.0] * 6,
            "gust_kt": [15.0] * 6,
            "wind_dir_deg": [270.0] * 6,
            "visibility_m": [10000.0] * 6,
        })

    def test_no_marine_no_tides_returns_weather(self):
        df_w = self._weather_df()
        merged = merge_to_hourly(df_w)
        assert list(merged.columns) == list(df_w.columns)

    def test_merge_with_marine_adds_wave_columns(self):
        df_w = self._weather_df()
        df_m = pd.DataFrame({
            "timestamp": pd.date_range("2026-05-15T00:00", periods=6, freq="h"),
            "wave_height_m": [0.5] * 6,
            "wave_period_s": [8.0] * 6,
            "wave_dir_deg": [280.0] * 6,
            "swell_height_m": [0.3] * 6,
            "sea_level_m": [0.5] * 6,
        })
        merged = merge_to_hourly(df_w, df_marine=df_m)
        assert "wave_height_m" in merged.columns
        assert len(merged) == len(df_w)

    def test_merge_with_tides_adds_tide_columns(self):
        df_w = self._weather_df()
        df_t = pd.DataFrame({
            "timestamp": pd.date_range("2026-05-15T00:00", periods=6, freq="h"),
            "tide_height_m": [0.5, 0.8, 1.1, 1.3, 1.2, 1.0],
            "tide_rate_m_per_h": [0.0, 0.3, 0.3, 0.2, -0.1, -0.2],
            "current_speed_kt": [0.0, 3.0, 3.0, 2.0, 1.0, 2.0],
        })
        merged = merge_to_hourly(df_w, df_tides=df_t)
        assert "tide_height_m" in merged.columns
        assert "current_speed_kt" in merged.columns

