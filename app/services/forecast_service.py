"""Forecast orchestration: fetch → normalize → score → return."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from app.domain.normalize import open_meteo_response_to_df
from app.domain.regions import SailingRegion, SailingZone
from app.domain.scoring import (
    add_sailability_to_hourly,
    best_windows,
    daily_sailability_avg,
    verdict,
)
from app.infra.config import load_config
from app.infra.open_meteo_client import fetch_forecast


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
    df_hourly: pd.DataFrame          # scored hourly DataFrame
    df_daily: pd.DataFrame           # daily aggregate (date, sailability_avg)
    best_sail_windows: list[tuple[pd.Timestamp, pd.Timestamp, float]]
    current_sailability: float       # average sailability for the next 6 hours
    verdict: str                     # "GO" | "MAYBE" | "NO-GO"


def _fetch_and_score(
    zone: SailingZone,
    region: SailingRegion,
    options: ForecastOptions,
    session: Any,
) -> ZoneForecast:
    raw = fetch_forecast(
        zone.latitude,
        zone.longitude,
        days=options.days,
        timezone=options.timezone,
        session=session,
    )
    df_hourly = open_meteo_response_to_df(raw)
    df_hourly = add_sailability_to_hourly(df_hourly)

    windows = best_windows(df_hourly, window_hours=3, top_n=3)
    df_daily = daily_sailability_avg(df_hourly)

    # Sailability over the next 6 hours for the hero card
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
    days: int,
    forecast_timezone: str,
) -> ZoneForecast:
    """Cached forecast fetch for a single zone.

    Streamlit cache_data cannot serialise dataclasses directly so we pass
    primitive arguments and reconstruct the domain objects inside.
    """
    from app.domain.regions import SailingRegion, SailingZone

    zone = SailingZone(
        id=zone_id,
        name=zone_name,
        latitude=lat,
        longitude=lon,
        exposure=exposure,
        hazards=list(hazards),
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


def get_default_zone_forecast(
    region: SailingRegion,
    days: int = 7,
) -> ZoneForecast:
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
        days=days,
        forecast_timezone=region.timezone,
    )
