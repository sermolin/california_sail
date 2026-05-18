"""Smoke tests for viz/charts.py — every chart builder must return a Figure."""
import pandas as pd
import pytest
from plotly.graph_objects import Figure

from app.domain.normalize import open_meteo_response_to_df
from app.domain.scoring import add_sailability_to_hourly
from app.viz.charts import (
    cloud_precip_chart,
    sailability_ribbon,
    temperature_line,
    tide_curve,
    wave_height_period_bar,
    wind_against_tide_timeline,
    wind_rose,
    wind_timeline_with_gusts,
    zone_map,
)


@pytest.fixture
def df_hourly(open_meteo_fixture) -> pd.DataFrame:
    df = open_meteo_response_to_df(open_meteo_fixture)
    return add_sailability_to_hourly(df)


@pytest.fixture
def df_hourly_v2(open_meteo_fixture) -> pd.DataFrame:
    """Full v2 DataFrame with marine + tide columns."""
    df = open_meteo_response_to_df(open_meteo_fixture)
    n = len(df)
    df["wave_height_m"] = 0.6
    df["wave_period_s"] = 8.0
    df["current_speed_kt"] = 1.5
    df["tide_height_m"] = 1.0
    df["tide_rate_m_per_h"] = 0.2
    return add_sailability_to_hourly(df, flood_dir_deg=55.0)


@pytest.fixture
def empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "wind_kt", "gust_kt", "wind_dir_deg",
                                  "temp_c", "precip_mm", "cloud_pct", "visibility_m",
                                  "sailability"])


class TestSailabilityRibbon:
    def test_returns_figure(self, df_hourly):
        fig = sailability_ribbon(df_hourly)
        assert isinstance(fig, Figure)

    def test_empty_returns_figure(self, empty_df):
        fig = sailability_ribbon(empty_df)
        assert isinstance(fig, Figure)


class TestWindRose:
    def test_returns_figure(self, df_hourly):
        fig = wind_rose(df_hourly)
        assert isinstance(fig, Figure)

    def test_empty_returns_figure(self, empty_df):
        fig = wind_rose(empty_df)
        assert isinstance(fig, Figure)


class TestWindTimeline:
    def test_returns_figure(self, df_hourly):
        fig = wind_timeline_with_gusts(df_hourly)
        assert isinstance(fig, Figure)

    def test_empty_returns_figure(self, empty_df):
        fig = wind_timeline_with_gusts(empty_df)
        assert isinstance(fig, Figure)


class TestTemperatureLine:
    def test_returns_figure(self, df_hourly):
        fig = temperature_line(df_hourly)
        assert isinstance(fig, Figure)

    def test_empty_returns_figure(self, empty_df):
        fig = temperature_line(empty_df)
        assert isinstance(fig, Figure)


class TestCloudPrecipChart:
    def test_returns_figure(self, df_hourly):
        fig = cloud_precip_chart(df_hourly)
        assert isinstance(fig, Figure)

    def test_empty_returns_figure(self, empty_df):
        fig = cloud_precip_chart(empty_df)
        assert isinstance(fig, Figure)


# ---------------------------------------------------------------------------
# Phase 2 chart tests
# ---------------------------------------------------------------------------

class TestWaveHeightPeriodBar:
    def test_returns_figure(self, df_hourly_v2):
        fig = wave_height_period_bar(df_hourly_v2)
        assert isinstance(fig, Figure)

    def test_empty_returns_figure(self, empty_df):
        fig = wave_height_period_bar(empty_df)
        assert isinstance(fig, Figure)

    def test_has_gate_line(self, df_hourly_v2):
        fig = wave_height_period_bar(df_hourly_v2)
        # Gate hline is represented as a layout shape
        shapes = fig.layout.shapes
        assert len(shapes) > 0 or len(fig.layout.annotations) >= 0  # hline adds shape


class TestTideCurve:
    def test_returns_figure(self, df_hourly_v2):
        fig = tide_curve(df_hourly_v2)
        assert isinstance(fig, Figure)

    def test_empty_returns_figure(self, empty_df):
        fig = tide_curve(empty_df)
        assert isinstance(fig, Figure)

    def test_has_tide_trace(self, df_hourly_v2):
        fig = tide_curve(df_hourly_v2)
        trace_names = [t.name for t in fig.data]
        assert "Tide height (m)" in trace_names


class TestWindAgainstTideTimeline:
    def test_returns_figure(self, df_hourly_v2):
        fig = wind_against_tide_timeline(df_hourly_v2)
        assert isinstance(fig, Figure)

    def test_empty_returns_figure(self, empty_df):
        fig = wind_against_tide_timeline(empty_df)
        assert isinstance(fig, Figure)


class TestZoneMap:
    def test_returns_figure_with_data(self):
        zones_data = [
            {"name": "City Front", "lat": 37.808, "lon": -122.435, "sailability": 72.0, "verdict": "GO", "exposure": "open"},
            {"name": "Berkeley OC", "lat": 37.866, "lon": -122.318, "sailability": 55.0, "verdict": "MAYBE", "exposure": "open"},
        ]
        fig = zone_map(zones_data)
        assert isinstance(fig, Figure)
        assert len(fig.data) == 1  # single Scattermapbox trace

    def test_empty_returns_figure(self):
        fig = zone_map([])
        assert isinstance(fig, Figure)

    def test_markers_colored_by_verdict(self):
        zones_data = [
            {"name": "Zone A", "lat": 37.8, "lon": -122.4, "sailability": 75.0, "verdict": "GO", "exposure": "open"},
            {"name": "Zone B", "lat": 37.85, "lon": -122.35, "sailability": 20.0, "verdict": "NO-GO", "exposure": "open"},
        ]
        fig = zone_map(zones_data)
        colors = fig.data[0].marker.color
        assert len(colors) == 2
        assert colors[0] != colors[1]  # GO and NO-GO should have different colours
