"""Tests for domain/normalize.py."""
import pandas as pd
import pytest

from app.domain.normalize import open_meteo_response_to_df


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
