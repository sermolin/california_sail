"""Normalize API responses into canonical pandas DataFrames."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.domain.units import ms_to_knots


# ---------------------------------------------------------------------------
# Open-Meteo weather → DataFrame
# ---------------------------------------------------------------------------

def open_meteo_response_to_df(raw: dict) -> pd.DataFrame:
    """Convert Open-Meteo hourly weather response to canonical sailing DataFrame.

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
# Open-Meteo Marine → DataFrame
# ---------------------------------------------------------------------------

def marine_response_to_df(raw: dict) -> pd.DataFrame:
    """Convert Open-Meteo Marine hourly response to canonical marine DataFrame.

    Output columns:
        timestamp       : tz-naive datetime
        wave_height_m   : significant wave height (m)
        wave_period_s   : dominant wave period (s); short period = chop
        wave_dir_deg    : wave direction (degrees FROM)
        swell_height_m  : swell wave height (m)
        sea_level_m     : sea level height above MSL (m); used as Sardinia tide proxy
    """
    hourly = raw.get("hourly") or {}
    time_arr = hourly.get("time") or []
    n = len(time_arr)
    if n == 0:
        return pd.DataFrame(columns=[
            "timestamp", "wave_height_m", "wave_period_s",
            "wave_dir_deg", "swell_height_m", "sea_level_m",
        ])

    def _arr(key: str, default: float = 0.0) -> list[float]:
        vals = hourly.get(key, [default] * n)
        if len(vals) != n:
            vals = list(vals) + [default] * (n - len(vals))
        return [float(v) if v is not None else default for v in vals]

    return pd.DataFrame({
        "timestamp": pd.to_datetime(time_arr),
        "wave_height_m": _arr("wave_height", 0.0),
        "wave_period_s": _arr("wave_period", 8.0),   # default to 8s (non-choppy)
        "wave_dir_deg": _arr("wave_direction", 0.0),
        "swell_height_m": _arr("swell_wave_height", 0.0),
        "sea_level_m": _arr("sea_level_height_msl", 0.0),
    })


# ---------------------------------------------------------------------------
# NOAA Tides → DataFrame
# ---------------------------------------------------------------------------

def noaa_tides_to_df(raw: dict) -> pd.DataFrame:
    """Convert NOAA CO-OPS predictions response to canonical tides DataFrame.

    Derives tidal current speed from the rate of change of water level:
        current_speed_kt ≈ |Δheight_m/hr| × CURRENT_SCALE
    A positive rate means the tide is rising (flood). The actual current
    direction is determined in scoring using the zone's flood_dir_deg.

    Output columns:
        timestamp         : tz-naive datetime (local standard/daylight time)
        tide_height_m     : predicted water level above MLLW (m)
        tide_rate_m_per_h : rate of change of tide height (m/hr); + = flooding
        current_speed_kt  : approximate tidal current speed (knots)
    """
    predictions = raw.get("predictions") or []
    if not predictions:
        return pd.DataFrame(columns=[
            "timestamp", "tide_height_m", "tide_rate_m_per_h", "current_speed_kt",
        ])

    timestamps = []
    heights: list[float] = []
    for entry in predictions:
        t_str = entry.get("t", "")
        v_str = entry.get("v", "0")
        try:
            timestamps.append(pd.to_datetime(t_str))
            heights.append(float(v_str))
        except (ValueError, TypeError):
            continue

    if not timestamps:
        return pd.DataFrame(columns=[
            "timestamp", "tide_height_m", "tide_rate_m_per_h", "current_speed_kt",
        ])

    df = pd.DataFrame({"timestamp": timestamps, "tide_height_m": heights})
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Hourly rate of change (m/hr) — forward difference, last row gets same as second-to-last
    heights_arr = df["tide_height_m"].to_numpy(dtype=float)
    rate = np.diff(heights_arr, prepend=heights_arr[0])  # same length as heights
    df["tide_rate_m_per_h"] = rate

    # Approximate current speed: SF Bay max rate ≈ 0.3 m/hr → ~3 kt → scale × 10
    # Clamp to 5 kt max to avoid absurd values from bad data
    CURRENT_SCALE = 10.0
    df["current_speed_kt"] = np.clip(np.abs(rate) * CURRENT_SCALE, 0.0, 5.0)

    return df


# ---------------------------------------------------------------------------
# Merge all sources into a single hourly DataFrame
# ---------------------------------------------------------------------------

def merge_to_hourly(
    df_weather: pd.DataFrame,
    df_marine: pd.DataFrame | None = None,
    df_tides: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge weather, marine, and tides DataFrames on timestamp.

    All DataFrames are expected to have a 'timestamp' column.
    Tides are often at hourly intervals but may not align perfectly with
    the weather timestamps; forward-fill is applied after the join.
    """
    df = df_weather.copy()

    if df_marine is not None and not df_marine.empty:
        # Normalise both timestamps to nanoseconds precision before merge
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.floor("h")
        df_m = df_marine.copy()
        df_m["timestamp"] = pd.to_datetime(df_m["timestamp"]).dt.floor("h")
        df = df.merge(df_m, on="timestamp", how="left")

    if df_tides is not None and not df_tides.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.floor("h")
        df_t = df_tides.copy()
        df_t["timestamp"] = pd.to_datetime(df_t["timestamp"]).dt.floor("h")
        df = df.merge(df_t, on="timestamp", how="left")
        # Forward-fill tide columns in case of any hourly gaps
        tide_cols = [c for c in df.columns if c.startswith("tide_") or c == "current_speed_kt"]
        df[tide_cols] = df[tide_cols].ffill()

    return df
