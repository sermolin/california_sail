"""Open-Meteo weather forecast API client."""
from __future__ import annotations

from typing import Any

from app.infra.http import ApiUnavailableError, create_session, get_json

BASE_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARIABLES = (
    "wind_speed_10m,"
    "wind_gusts_10m,"
    "wind_direction_10m,"
    "temperature_2m,"
    "precipitation,"
    "cloud_cover,"
    "visibility"
)


class InvalidApiResponseError(Exception):
    """Raised when the API response is missing required fields."""


def _validate_response(raw: dict) -> None:
    hourly = raw.get("hourly")
    if not hourly or not isinstance(hourly, dict):
        raise InvalidApiResponseError("Missing or invalid 'hourly' in Open-Meteo response")
    required = {"time", "wind_speed_10m", "temperature_2m"}
    missing = required - set(hourly.keys())
    if missing:
        raise InvalidApiResponseError(
            f"Open-Meteo hourly response missing fields: {missing}"
        )


def fetch_forecast(
    latitude: float,
    longitude: float,
    days: int = 7,
    timezone: str = "America/Los_Angeles",
    *,
    session: Any = None,
) -> dict:
    """Fetch hourly weather forecast from Open-Meteo. Returns raw JSON dict."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "forecast_days": min(16, max(1, days)),
        "timezone": timezone,
        "hourly": HOURLY_VARIABLES,
    }
    if session is None:
        session = create_session()
    raw = get_json(session, BASE_URL, params=params)
    _validate_response(raw)
    return raw
