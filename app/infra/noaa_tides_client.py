"""NOAA CO-OPS Tides & Currents API client.

Fetches hourly tide water-level PREDICTIONS for a US station.
Tidal current speed is approximated from the rate-of-change of the water level
(see noaa_tides_to_df in normalize.py for the derivation).

API reference: https://api.tidesandcurrents.noaa.gov/api/prod/
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.infra.http import ApiUnavailableError, create_session, get_json

NOAA_API_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


class InvalidNoaaTidesResponseError(Exception):
    """Raised when the NOAA response is missing the expected structure."""


def _validate_tides_response(raw: dict) -> None:
    if "predictions" not in raw:
        err = raw.get("error", {})
        msg = err.get("message", str(raw)[:200]) if isinstance(err, dict) else str(err)[:200]
        raise InvalidNoaaTidesResponseError(
            f"NOAA tides response missing 'predictions': {msg}"
        )
    if not isinstance(raw["predictions"], list) or len(raw["predictions"]) == 0:
        raise InvalidNoaaTidesResponseError(
            "NOAA tides 'predictions' is empty or not a list"
        )


def fetch_tide_predictions(
    station_id: str,
    days: int = 7,
    timezone: str = "lst_ldt",
    *,
    session: Any = None,
    reference_date: date | None = None,
) -> dict:
    """Fetch hourly tide water-level predictions from NOAA CO-OPS.

    Args:
        station_id:     NOAA CO-OPS station id, e.g. "9414290" (San Francisco).
        days:           Number of forecast days (1–10; NOAA predictions are available
                        weeks in advance).
        timezone:       "lst_ldt" (local standard/daylight time) or "gmt".
        session:        Optional requests.Session for test injection.
        reference_date: Start date (defaults to today). Used in tests to freeze time.

    Returns:
        Raw NOAA JSON dict with a 'predictions' list of {t, v} objects.
    """
    start = reference_date or date.today()
    end = start + timedelta(days=max(1, days))

    params = {
        "product": "predictions",
        "application": "california_sail",
        "begin_date": start.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "datum": "MLLW",
        "station": station_id,
        "time_zone": timezone,
        "interval": "h",
        "units": "metric",
        "format": "json",
    }
    if session is None:
        session = create_session()
    raw = get_json(session, NOAA_API_URL, params=params)
    _validate_tides_response(raw)
    return raw
