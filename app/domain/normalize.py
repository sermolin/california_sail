"""Normalize API responses into canonical pandas DataFrames."""
from __future__ import annotations

import pandas as pd

from app.domain.units import ms_to_knots


def open_meteo_response_to_df(raw: dict) -> pd.DataFrame:
    """Convert Open-Meteo hourly response to canonical sailing DataFrame.

    Output columns:
        timestamp       : tz-naive datetime (local time as returned by Open-Meteo)
        wind_kt         : mean wind speed at 10 m (knots)
        gust_kt         : wind gust at 10 m (knots)
        wind_dir_deg    : meteorological wind direction 0-360 (degrees FROM)
        temp_c          : air temperature at 2 m (°C)
        precip_mm       : precipitation (mm)
        cloud_pct       : cloud cover (%)
        visibility_m    : horizontal visibility (m)
    """
    hourly = raw.get("hourly") or {}
    time_arr = hourly.get("time") or []
    n = len(time_arr)
    if n == 0:
        return pd.DataFrame(columns=[
            "timestamp", "wind_kt", "gust_kt", "wind_dir_deg",
            "temp_c", "precip_mm", "cloud_pct", "visibility_m",
        ])

    def _arr(key: str, default: float = 0.0) -> list[float]:
        vals = hourly.get(key, [default] * n)
        if len(vals) != n:
            vals = list(vals) + [default] * (n - len(vals))
        return [float(v) if v is not None else default for v in vals]

    def _arr_nullable(key: str) -> list[float]:
        vals = hourly.get(key, [None] * n)
        if len(vals) != n:
            vals = list(vals) + [None] * (n - len(vals))
        return [float(v) if v is not None else float("nan") for v in vals]

    wind_ms = _arr("wind_speed_10m", 0.0)
    gust_ms = _arr("wind_gusts_10m", 0.0)

    return pd.DataFrame({
        "timestamp": pd.to_datetime(time_arr),
        "wind_kt": [ms_to_knots(v) for v in wind_ms],
        "gust_kt": [ms_to_knots(v) for v in gust_ms],
        "wind_dir_deg": _arr("wind_direction_10m", 0.0),
        "temp_c": _arr_nullable("temperature_2m"),
        "precip_mm": _arr("precipitation", 0.0),
        "cloud_pct": _arr("cloud_cover", 0.0),
        "visibility_m": _arr("visibility", 10000.0),
    })


# ---------------------------------------------------------------------------
# Phase 2 stubs — implemented in Phase 2 when marine + tides data arrives
# ---------------------------------------------------------------------------

def marine_response_to_df(raw: dict) -> pd.DataFrame:
    """Stub: convert Open-Meteo Marine hourly response to DataFrame (Phase 2)."""
    return pd.DataFrame(columns=[
        "timestamp", "wave_height_m", "wave_period_s",
        "wave_dir_deg", "swell_height_m", "sea_level_m",
    ])


def noaa_tides_to_df(raw: dict) -> pd.DataFrame:
    """Stub: convert NOAA tides/currents response to DataFrame (Phase 2)."""
    return pd.DataFrame(columns=[
        "timestamp", "tide_height_m", "current_speed_kt", "current_dir_deg",
    ])


def merge_to_hourly(
    df_weather: pd.DataFrame,
    df_marine: pd.DataFrame | None = None,
    df_tides: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge weather, marine, and tides DataFrames on timestamp (Phase 2 stub).

    In Phase 1 only df_weather is provided; the function returns it unchanged.
    """
    if df_marine is None and df_tides is None:
        return df_weather
    df = df_weather.copy()
    if df_marine is not None and not df_marine.empty:
        df = df.merge(df_marine, on="timestamp", how="left")
    if df_tides is not None and not df_tides.empty:
        df = df.merge(df_tides, on="timestamp", how="left")
    return df
