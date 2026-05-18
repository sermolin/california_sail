"""Forecast orchestration v2: concurrent multi-source fetch → normalize → score → return."""
from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from app.domain.normalize import marine_response_to_df, merge_to_hourly, noaa_tides_to_df, open_meteo_response_to_df
from app.domain.regions import SailingRegion, SailingZone
from app.domain.scoring import (
    add_sailability_to_hourly,
    best_windows,
    daily_sailability_avg,
    verdict,
)
from app.infra.config import load_config
from app.infra.http import ApiUnavailableError
from app.infra.open_meteo_client import fetch_forecast
from app.infra.open_meteo_marine_client import fetch_marine_forecast
from app.infra.noaa_tides_client import fetch_tide_predictions

_log = logging.getLogger(__name__)


@dataclass
class ForecastOptions:
    """Options for a forecast request."""

    days: int = 7
    timezone: str = "America/Los_Angeles"


@dataclass
class ZoneForecast:
    """All data for a single sailing zone."""

    zone: SailingZone
    region: SailingRegion
    df_hourly: pd.DataFrame
    df_daily: pd.DataFrame
    best_sail_windows: list[tuple[pd.Timestamp, pd.Timestamp, float]]
    current_sailability: float
    verdict: str
    has_marine_data: bool = False
    has_tide_data: bool = False


def _fetch_and_score(
    zone: SailingZone,
    region: SailingRegion,
    options: ForecastOptions,
    session: Any,
) -> ZoneForecast:
    """Fetch all available sources concurrently, merge, score, and return ZoneForecast."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        future_weather = pool.submit(
            fetch_forecast,
            zone.latitude, zone.longitude,
            days=options.days, timezone=options.timezone, session=session,
        )
        future_marine = pool.submit(
            fetch_marine_forecast,
            zone.latitude, zone.longitude,
            days=options.days, timezone=options.timezone, session=session,
        )
        future_tides = (
            pool.submit(
                fetch_tide_predictions,
                region.tide_station_id,
                days=options.days,
                session=session,
            )
            if region.has_noaa_tides()
            else None
        )

        # --- Weather (required) ---
        raw_weather = future_weather.result()
        df_weather = open_meteo_response_to_df(raw_weather)

        # --- Marine (optional — degrades gracefully) ---
        df_marine: pd.DataFrame | None = None
        has_marine = False
        try:
            raw_marine = future_marine.result()
            df_marine = marine_response_to_df(raw_marine)
            has_marine = not df_marine.empty
        except Exception as e:
            _log.warning("Marine forecast unavailable for %s: %s", zone.id, e)

        # --- NOAA tides (optional — US only) ---
        df_tides: pd.DataFrame | None = None
        has_tides = False
        if future_tides is not None:
            try:
                raw_tides = future_tides.result()
                df_tides = noaa_tides_to_df(raw_tides)
                has_tides = not df_tides.empty
            except Exception as e:
                _log.warning("NOAA tides unavailable for %s: %s", zone.id, e)

    # --- Merge ---
    df_hourly = merge_to_hourly(df_weather, df_marine, df_tides)

    # --- Score ---
    df_hourly = add_sailability_to_hourly(df_hourly, flood_dir_deg=zone.flood_dir_deg)

    windows = best_windows(df_hourly, window_hours=3, top_n=3)
    df_daily = daily_sailability_avg(df_hourly)

    now_score = (
        float(df_hourly["sailability"].iloc[:6].mean())
        if not df_hourly.empty
        else 0.0
    )

    return ZoneForecast(
        zone=zone,
        region=region,
        df_hourly=df_hourly,
        df_daily=df_daily,
        best_sail_windows=windows,
        current_sailability=now_score,
        verdict=verdict(now_score),
        has_marine_data=has_marine,
        has_tide_data=has_tides,
    )


@st.cache_data(ttl=load_config().cache_ttl_seconds, show_spinner=False)
def get_zone_forecast(
    zone_id: str,
    region_id: str,
    lat: float,
    lon: float,
    zone_name: str,
    region_name: str,
    country: str,
    timezone: str,
    tide_station_id: str | None,
    nws_zone: str | None,
    exposure: str,
    hazards: tuple[str, ...],
    flood_dir_deg: float | None,
    days: int,
    forecast_timezone: str,
) -> ZoneForecast:
    """Cached forecast fetch for a single zone (all primitive args for st.cache_data)."""
    zone = SailingZone(
        id=zone_id,
        name=zone_name,
        latitude=lat,
        longitude=lon,
        exposure=exposure,
        hazards=list(hazards),
        flood_dir_deg=flood_dir_deg,
    )
    region = SailingRegion(
        id=region_id,
        name=region_name,
        country=country,
        timezone=timezone,
        tide_station_id=tide_station_id,
        nws_zone=nws_zone,
        zones=[zone],
    )
    opts = ForecastOptions(days=days, timezone=forecast_timezone)
    return _fetch_and_score(zone, region, opts, session=None)


def get_default_zone_forecast(region: SailingRegion, days: int = 7) -> ZoneForecast:
    """Convenience: fetch the default (first) zone of a region."""
    zone = region.default_zone
    return get_zone_forecast(
        zone_id=zone.id,
        region_id=region.id,
        lat=zone.latitude,
        lon=zone.longitude,
        zone_name=zone.name,
        region_name=region.name,
        country=region.country,
        timezone=region.timezone,
        tide_station_id=region.tide_station_id,
        nws_zone=region.nws_zone,
        exposure=zone.exposure,
        hazards=tuple(zone.hazards),
        flood_dir_deg=zone.flood_dir_deg,
        days=days,
        forecast_timezone=region.timezone,
    )
