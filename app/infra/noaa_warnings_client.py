"""NOAA Weather.gov Alerts API client — marine warnings for US zones.

Fetches active alerts for a NOAA NWS marine zone (e.g. "PZZ545") from:
  https://api.weather.gov/alerts/active?zone={nws_zone}

The response is a GeoJSON FeatureCollection.  Each Feature's `properties`
contains the alert metadata.  We extract only the fields relevant for
the sailing warnings panel.

Relevant event types (not exhaustive):
  - Small Craft Advisory
  - Brisk Wind Advisory
  - Gale Warning
  - Storm Warning
  - Hurricane Force Wind Warning
  - Special Marine Warning
  - Dense Fog Advisory
  - Hazardous Seas Warning
"""
from __future__ import annotations

from typing import Any

from app.infra.http import ApiUnavailableError, create_session, get_json

NOAA_ALERTS_URL = "https://api.weather.gov/alerts/active"

# Severity ordering for sort (highest first)
_SEVERITY_ORDER = {
    "Extreme": 0,
    "Severe": 1,
    "Moderate": 2,
    "Minor": 3,
    "Unknown": 4,
}

MARINE_EVENT_KEYWORDS = {
    "small craft",
    "brisk wind",
    "gale",
    "storm warning",
    "hurricane force",
    "special marine",
    "dense fog",
    "hazardous seas",
    "wind advisory",
    "wind warning",
}


class InvalidNoaaWarningsResponseError(Exception):
    """Raised when the NOAA alerts response is missing expected structure."""


def _validate_warnings_response(raw: dict) -> None:
    if raw.get("type") != "FeatureCollection":
        raise InvalidNoaaWarningsResponseError(
            f"Expected GeoJSON FeatureCollection, got type={raw.get('type')!r}"
        )
    if "features" not in raw:
        raise InvalidNoaaWarningsResponseError("Missing 'features' in NOAA alerts response")


def _parse_feature(feature: dict) -> dict | None:
    """Extract a simplified warning dict from a GeoJSON Feature.

    Returns None if the event is not marine-relevant.
    """
    props = feature.get("properties") or {}
    event = str(props.get("event", "")).lower()

    if not any(kw in event for kw in MARINE_EVENT_KEYWORDS):
        return None

    return {
        "event": props.get("event", "Unknown"),
        "headline": props.get("headline", ""),
        "description": (props.get("description") or "")[:400],
        "severity": props.get("severity", "Unknown"),
        "urgency": props.get("urgency", "Unknown"),
        "effective": props.get("effective", ""),
        "expires": props.get("expires", ""),
        "status": props.get("status", "Actual"),
    }


def fetch_marine_warnings(
    nws_zone: str,
    *,
    session: Any = None,
) -> list[dict]:
    """Fetch active marine warnings for a NOAA NWS marine zone.

    Returns a list of simplified warning dicts, sorted by severity (worst first).
    Returns an empty list if there are no active marine warnings.

    Never raises — API errors are caught and return an empty list so the app
    degrades gracefully when the NOAA Alerts API is unavailable.
    """
    if not nws_zone:
        return []

    try:
        if session is None:
            session = create_session()
        raw = get_json(
            session,
            NOAA_ALERTS_URL,
            params={"zone": nws_zone},
            headers={"Accept": "application/geo+json"},
        )
        _validate_warnings_response(raw)
    except Exception:
        return []

    warnings: list[dict] = []
    for feature in raw.get("features", []):
        parsed = _parse_feature(feature)
        if parsed and parsed.get("status") == "Actual":
            warnings.append(parsed)

    warnings.sort(key=lambda w: _SEVERITY_ORDER.get(w["severity"], 99))
    return warnings
