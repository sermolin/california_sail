"""Forecast orchestration v3: concurrent multi-source fetch → normalize → profile-scored → return.

v3 adds:
  - SailorProfile parameter drives scoring thresholds
  - NOAA marine warnings fetch as 4th concurrent call (US regions only)
  - ZoneForecast gains `warnings` and `profile` fields
"""
from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import streamlit as st

from app.domain.normalize import (
    marine_response_to_df,
    merge_to_hourly,
    noaa_tides_to_df,
    open_meteo_response_to_df,
)
from app.domain.profiles import SailorProfile, get_default_profile, get_profile_by_id
from app.domain.regions import SailingRegion, SailingZone
from app.domain.scoring import add_sailability_to_hourly, best_windows, daily_sailability_avg, verdict
from app.infra.config import load_config
from app.infra.noaa_tides_client import fetch_tide_predictions
from app.infra.noaa_warnings_client import fetch_marine_warnings
from app.infra.open_meteo_client import fetch_forecast
from app.infra.open_meteo_marine_client import fetch_marine_forecast

_log = logging.getLogger(__name__)


@dataclass
class ForecastOptions:
    days: int = 7
    timezone: str = "America/Los_Angeles"


@dataclass
class ZoneForecast:
    zone: SailingZone
    region: SailingRegion
    df_hourly: pd.DataFrame
    df_daily: pd.DataFrame
    best_sail_windows: list[tuple[pd.Timestamp, pd.Timestamp, float]]
    current_sailability: float
    verdict: str
    has_marine_data: bool = False
    has_tide_data: bool = False
    warnings: list[dict] = field(default_factory=list)
    profile: SailorProfile | None = None


def _fetch_and_score(
    zone: SailingZone,
    region: SailingRegion,
    options: ForecastOptions,
    session: Any,
    profile: SailorProfile,
) -> ZoneForecast:
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
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
            pool.submit(fetch_tide_predictions, region.tide_station_id, days=options.days, session=session)
            if region.has_noaa_tides()
            else None
        )
        future_warnings = (
            pool.submit(fetch_marine_warnings, region.nws_zone, session=session)
            if region.nws_zone
            else None
        )

        raw_weather = future_weather.result()
        df_weather = open_meteo_response_to_df(raw_weather)

        df_marine: pd.DataFrame | None = None
        has_marine = False
        try:
            df_marine = marine_response_to_df(future_marine.result())
            has_marine = not df_marine.empty
        except Exception as e:
            _log.warning("Marine forecast unavailable for %s: %s", zone.id, e)

        df_tides: pd.DataFrame | None = None
        has_tides = False
        if future_tides is not None:
            try:
                df_tides = noaa_tides_to_df(future_tides.result())
                has_tides = not df_tides.empty
            except Exception as e:
                _log.warning("NOAA tides unavailable for %s: %s", zone.id, e)

        warnings: list[dict] = []
        if future_warnings is not None:
            try:
                warnings = future_warnings.result() or []
            except Exception as e:
                _log.warning("NOAA warnings unavailable for %s: %s", region.nws_zone, e)

    df_hourly = merge_to_hourly(df_weather, df_marine, df_tides)
    df_hourly = add_sailability_to_hourly(df_hourly, flood_dir_deg=zone.flood_dir_deg, profile=profile)

    windows = best_windows(df_hourly, window_hours=3, top_n=3)
    df_daily = daily_sailability_avg(df_hourly)
    now_score = float(df_hourly["sailability"].iloc[:6].mean()) if not df_hourly.empty else 0.0

    return ZoneForecast(
        zone=zone, region=region,
        df_hourly=df_hourly, df_daily=df_daily,
        best_sail_windows=windows,
        current_sailability=now_score,
        verdict=verdict(now_score),
        has_marine_data=has_marine,
        has_tide_data=has_tides,
        warnings=warnings,
        profile=profile,
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
    profile_id: str = "cruiser",
) -> ZoneForecast:
    """Cached forecast fetch for a single zone (all primitive args for st.cache_data)."""
    zone = SailingZone(
        id=zone_id, name=zone_name, latitude=lat, longitude=lon,
        exposure=exposure, hazards=list(hazards), flood_dir_deg=flood_dir_deg,
    )
    region = SailingRegion(
        id=region_id, name=region_name, country=country, timezone=timezone,
        tide_station_id=tide_station_id, nws_zone=nws_zone, zones=[zone],
    )
    profile = get_profile_by_id(profile_id)
    opts = ForecastOptions(days=days, timezone=forecast_timezone)
    return _fetch_and_score(zone, region, opts, session=None, profile=profile)


def get_default_zone_forecast(
    region: SailingRegion,
    days: int = 7,
    profile: SailorProfile | None = None,
) -> ZoneForecast:
    """Convenience: fetch the default (first) zone of a region."""
    if profile is None:
        profile = get_default_profile()
    zone = region.default_zone
    return get_zone_forecast(
        zone_id=zone.id, region_id=region.id,
        lat=zone.latitude, lon=zone.longitude,
        zone_name=zone.name, region_name=region.name,
        country=region.country, timezone=region.timezone,
        tide_station_id=region.tide_station_id, nws_zone=region.nws_zone,
        exposure=zone.exposure, hazards=tuple(zone.hazards),
        flood_dir_deg=zone.flood_dir_deg,
        days=days, forecast_timezone=region.timezone,
        profile_id=profile.id,
    )
