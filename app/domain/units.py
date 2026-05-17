"""Unit conversions and helpers for sailing weather data."""
from __future__ import annotations

import math

# -- Speed ------------------------------------------------------------------

def ms_to_knots(ms: float) -> float:
    """Convert meters per second to knots."""
    return ms * 1.94384


def kmh_to_knots(kmh: float) -> float:
    """Convert kilometers per hour to knots."""
    return kmh / 1.852


def knots_to_kmh(kt: float) -> float:
    """Convert knots to kilometers per hour."""
    return kt * 1.852


# -- Distance / height ------------------------------------------------------

def m_to_ft(m: float) -> float:
    """Convert meters to feet."""
    return m * 3.28084


# -- Temperature ------------------------------------------------------------

def c_to_f(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return c * 9.0 / 5.0 + 32.0


# -- Direction --------------------------------------------------------------

_COMPASS_LABELS = [
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW",
]


def deg_to_compass(deg: float) -> str:
    """Convert a meteorological wind direction (degrees) to a compass label.

    Wind direction is the direction the wind is coming FROM (met convention).
    0/360 = North, 90 = East, 180 = South, 270 = West.
    """
    idx = round(deg / 22.5) % 16
    return _COMPASS_LABELS[idx]


def signed_deg_diff(a: float, b: float) -> float:
    """Return the signed angular difference a - b in (-180, 180].

    Positive values mean a is clockwise of b, negative means counter-clockwise.
    Used to test wind-against-tide: if |diff| > 150 deg, directions are opposed.
    """
    diff = (a - b) % 360.0
    if diff > 180.0:
        diff -= 360.0
    return diff


def directions_opposed(wind_deg: float, current_deg: float, threshold_deg: float = 150.0) -> bool:
    """Return True when wind and current directions are approximately opposed.

    current_deg is the direction the current is flowing TO (oceanographic convention).
    wind_deg is the direction the wind is coming FROM (met convention).
    Wind-against-tide occurs when the wind blows opposite to the current flow direction,
    i.e. when wind FROM direction ≈ current TO direction + 180 deg.
    """
    flow_toward = (current_deg + 180.0) % 360.0  # where current comes FROM
    return abs(signed_deg_diff(wind_deg, flow_toward)) <= (180.0 - threshold_deg)
