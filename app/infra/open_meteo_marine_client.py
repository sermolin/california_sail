"""Open-Meteo Marine API client — wave and sea-level data."""
from __future__ import annotations

from typing import Any

from app.infra.http import ApiUnavailableError, create_session, get_json

MARINE_BASE_URL = "https://marine-api.open-meteo.com/v1/marine"

HOURLY_MARINE_VARIABLES = (
    "wave_height,"
    "wave_period,"
    "wave_direction,"
    "swell_wave_height,"
    "sea_level_height_msl"
)


class InvalidMarineApiResponseError(Exception):
    """Raised when the Marine API response is missing required fields."""


def _validate_marine_response(raw: dict) -> None:
    hourly = raw.get("hourly")
    if not hourly or not isinstance(hourly, dict):
        raise InvalidMarineApiResponseError(
            "Missing or invalid 'hourly' in Open-Meteo Marine response"
        )
    if "time" not in hourly:
        raise InvalidMarineApiResponseError(
            "Open-Meteo Marine response missing 'time' in hourly"
        )
    if "wave_height" not in hourly:
        raise InvalidMarineApiResponseError(
            "Open-Meteo Marine response missing 'wave_height' in hourly"
        )


def fetch_marine_forecast(
    latitude: float,
    longitude: float,
    days: int = 7,
    timezone: str = "America/Los_Angeles",
    *,
    session: Any = None,
) -> dict:
    """Fetch hourly marine forecast (waves, swell, sea level) from Open-Meteo Marine.

    Returns raw JSON dict. Raises InvalidMarineApiResponseError if required fields
    are missing. Not all locations have marine data; the caller should handle
    ApiUnavailableError and degrade gracefully.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "forecast_days": min(16, max(1, days)),
        "timezone": timezone,
        "hourly": HOURLY_MARINE_VARIABLES,
    }
    if session is None:
        session = create_session()
    raw = get_json(session, MARINE_BASE_URL, params=params)
    _validate_marine_response(raw)
    return raw
