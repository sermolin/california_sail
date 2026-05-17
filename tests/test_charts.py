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
    wind_rose,
    wind_timeline_with_gusts,
)


@pytest.fixture
def df_hourly(open_meteo_fixture) -> pd.DataFrame:
    df = open_meteo_response_to_df(open_meteo_fixture)
    return add_sailability_to_hourly(df)


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
