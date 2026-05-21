"""JSON-safe serializers for California Sail domain objects.

All public functions produce plain Python dicts/lists with only JSON-compatible
types (str, int, float, bool, None, list, dict).  No DataFrames, numpy types,
pandas Timestamps, or Python dataclasses are returned directly.

The primary entry-point is :func:`zone_forecast_to_dict` which can produce a
``summary`` view (no hourly data, tiny payload) or a ``full`` view (hourly rows
capped at 72 to keep payloads reasonable for LLMs).
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.domain.profiles import SailorProfile
from app.domain.regions import SailingRegion, SailingZone
from app.services.forecast_service import ZoneForecast

_HOURLY_CAP = 72  # max hourly rows sent over MCP


# ---------------------------------------------------------------------------
# Low-level scalar helpers
# ---------------------------------------------------------------------------

def _safe_float(v: Any, ndigits: int = 2) -> float | None:
    """Round a numeric value to *ndigits* decimal places; return None for NaN/inf."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, ndigits)


def _ts_iso(ts: Any) -> str | None:
    """Convert a pandas Timestamp (or anything with isoformat) to an ISO-8601 string."""
    if ts is None:
        return None
    if isinstance(ts, pd.Timestamp):
        return ts.isoformat()
    try:
        return ts.isoformat()
    except AttributeError:
        return str(ts)


# ---------------------------------------------------------------------------
# Domain-object serializers
# ---------------------------------------------------------------------------

def zone_to_dict(zone: SailingZone) -> dict[str, Any]:
    """Serialize a SailingZone to a JSON-safe dict."""
    return {
        "id": zone.id,
        "name": zone.name,
        "latitude": _safe_float(zone.latitude, 4),
        "longitude": _safe_float(zone.longitude, 4),
        "exposure": zone.exposure,
        "hazards": list(zone.hazards),
        "flood_dir_deg": _safe_float(zone.flood_dir_deg),
    }


def region_to_dict(region: SailingRegion, include_zones: bool = True) -> dict[str, Any]:
    """Serialize a SailingRegion to a JSON-safe dict."""
    d: dict[str, Any] = {
        "id": region.id,
        "name": region.name,
        "country": region.country,
        "timezone": region.timezone,
        "n_zones": len(region.zones),
    }
    if include_zones:
        d["zones"] = [zone_to_dict(z) for z in region.zones]
    return d


def profile_to_dict(profile: SailorProfile) -> dict[str, Any]:
    """Serialize a SailorProfile to a JSON-safe dict."""
    return {
        "id": profile.id,
        "name": profile.name,
        "emoji": profile.emoji,
        "boat_size_hint": profile.boat_size_hint,
        "ideal_wind_kt": list(profile.ideal_wind_kt),
        "max_gust_kt": _safe_float(profile.max_gust_kt),
        "max_wave_m": _safe_float(profile.max_wave_m),
        "min_visibility_km": _safe_float(profile.min_visibility_km),
        "requires_low_chop": profile.requires_low_chop,
        "chop_penalty": _safe_float(profile.chop_penalty),
        "chop_period_s": _safe_float(profile.chop_period_s),
        "wat_min_current_kt": _safe_float(profile.wat_min_current_kt),
    }


def _daily_rows(df_daily: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert the daily-summary DataFrame to a list of JSON-safe row dicts."""
    rows: list[dict[str, Any]] = []
    for _, row in df_daily.iterrows():
        rows.append({
            "date": str(row.name.date()) if hasattr(row.name, "date") else str(row.name),
            "sailability_avg": _safe_float(row.get("sailability")),
            "wind_kt_avg": _safe_float(row.get("wind_kt")),
            "gust_kt_max": _safe_float(row.get("gust_kt")),
            "wave_height_m_avg": _safe_float(row.get("wave_height_m")),
        })
    return rows


def _hourly_rows(df_hourly: pd.DataFrame, cap: int = _HOURLY_CAP) -> list[dict[str, Any]]:
    """Convert the hourly DataFrame (first *cap* rows) to a list of JSON-safe row dicts."""
    rows: list[dict[str, Any]] = []
    columns_wanted = [
        "wind_kt", "gust_kt", "wind_dir_deg",
        "wave_height_m", "wave_period_s",
        "tide_height_m",
        "visibility_m",
        "sailability", "wind_score", "sea_score", "visibility_score",
        "gates_passed", "wat_penalty",
    ]
    for _, row in df_hourly.head(cap).iterrows():
        r: dict[str, Any] = {
            "time": _ts_iso(row.name),
        }
        for col in columns_wanted:
            if col in df_hourly.columns:
                val = row[col]
                if col == "gates_passed":
                    r[col] = bool(val) if not _is_nan(val) else None
                else:
                    r[col] = _safe_float(val)
        rows.append(r)
    return rows


def _is_nan(v: Any) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def _best_windows_list(
    windows: list[tuple[pd.Timestamp, pd.Timestamp, float]],
) -> list[dict[str, Any]]:
    result = []
    for start, end, score in windows:
        result.append({
            "start": _ts_iso(start),
            "end": _ts_iso(end),
            "score": _safe_float(score),
        })
    return result


# ---------------------------------------------------------------------------
# Main serializer
# ---------------------------------------------------------------------------

def zone_forecast_to_dict(
    result: ZoneForecast,
    summary: bool = True,
    hourly_cap: int = _HOURLY_CAP,
) -> dict[str, Any]:
    """Serialize a ZoneForecast to a JSON-safe dict.

    Args:
        result: The ZoneForecast to serialize.
        summary: When True (default), omit per-hour rows — produces a compact
                 payload suitable for initial LLM context.  When False, include
                 hourly data capped at *hourly_cap* rows.
        hourly_cap: Maximum number of hourly rows to include (default 72 = 3 days).

    Returns:
        A dict that is safe to pass to ``json.dumps()`` with no custom encoder.
    """
    d: dict[str, Any] = {
        "zone": zone_to_dict(result.zone),
        "region": region_to_dict(result.region, include_zones=False),
        "profile": profile_to_dict(result.profile) if result.profile else None,
        "current_sailability": _safe_float(result.current_sailability),
        "verdict": result.verdict,
        "has_marine_data": result.has_marine_data,
        "has_tide_data": result.has_tide_data,
        "best_sail_windows": _best_windows_list(result.best_sail_windows),
        "daily": _daily_rows(result.df_daily),
        "warnings": _serialize_warnings(result.warnings),
    }
    if not summary:
        d["hourly"] = _hourly_rows(result.df_hourly, cap=hourly_cap)
    return d


def _serialize_warnings(warnings: list[dict]) -> list[dict[str, Any]]:
    """Strip any non-JSON-safe values from warning dicts."""
    safe = []
    for w in warnings:
        safe.append({
            "event": str(w.get("event", "")),
            "severity": str(w.get("severity", "")),
            "headline": str(w.get("headline", "")),
            "expires": str(w.get("expires", "")),
        })
    return safe
