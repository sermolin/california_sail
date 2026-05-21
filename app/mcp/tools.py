"""Pure tool functions for the California Sail MCP server.

Each function is a thin adapter that:
1. Validates inputs and raises ``ValueError`` with a helpful message on bad IDs.
2. Delegates to the appropriate service / domain function.
3. Returns a JSON-safe dict or list (no DataFrames, no numpy types).

The functions are deliberately decoupled from the MCP runtime so they can be
unit-tested without starting a server.  ``server.py`` registers them with
FastMCP.

Shared state
------------
A module-level :class:`TTLForecastCache` is used by all forecast tools so
repeated calls within the 15-minute TTL window are served from cache rather
than hitting live APIs.  This cache is shared within a single server process.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.domain.profiles import SailorProfile, get_all_profiles, get_profile_by_id
from app.domain.regions import SailingRegion, load_regions
from app.infra.forecast_cache import TTLForecastCache
from app.infra.noaa_warnings_client import fetch_marine_warnings
from app.mcp.serializers import (
    profile_to_dict,
    region_to_dict,
    zone_forecast_to_dict,
    zone_to_dict,
    _safe_float,
    _ts_iso,
)
from app.services.forecast_service import get_zone_forecast as _svc_get_zone_forecast
from app.services.region_service import get_all_zone_forecasts

_SAILING_AREAS_YAML = Path(__file__).resolve().parent.parent.parent / "data" / "sailing_areas.yaml"

# Shared process-level cache: 15-minute TTL, up to 256 entries.
_cache = TTLForecastCache(maxsize=256, ttl=900)

# Region/zone lookup helpers cached at module load.
_regions: list[SailingRegion] | None = None


def _get_regions() -> list[SailingRegion]:
    global _regions
    if _regions is None:
        _regions = load_regions(_SAILING_AREAS_YAML)
    return _regions


def _find_region(region_id: str) -> SailingRegion:
    """Return region by id or raise ValueError with available IDs."""
    for r in _get_regions():
        if r.id == region_id:
            return r
    available = ", ".join(r.id for r in _get_regions())
    raise ValueError(f"Unknown region_id {region_id!r}. Available: {available}")


def _find_zone_globally(zone_id: str) -> tuple[SailingRegion, Any]:
    """Return (region, zone) for a zone_id searched across all regions."""
    for r in _get_regions():
        for z in r.zones:
            if z.id == zone_id:
                return r, z
    available = ", ".join(z.id for r in _get_regions() for z in r.zones)
    raise ValueError(f"Unknown zone_id {zone_id!r}. Available: {available}")


# ---------------------------------------------------------------------------
# 1. list_regions
# ---------------------------------------------------------------------------

def list_regions() -> list[dict[str, Any]]:
    """List all available sailing regions.

    Returns a compact list of regions — one entry per region with its ID, name,
    country, and the number of sailing zones within it.  Use this to discover
    valid ``region_id`` values for other tools.

    Example response::

        [
          {"id": "sf-bay", "name": "San Francisco Bay", "country": "US", "n_zones": 4},
          {"id": "puget-sound", "name": "Puget Sound", "country": "US", "n_zones": 3},
          {"id": "sardinia", "name": "Sardinia", "country": "IT", "n_zones": 3},
        ]
    """
    return [
        {
            "id": r.id,
            "name": r.name,
            "country": r.country,
            "n_zones": len(r.zones),
        }
        for r in _get_regions()
    ]


# ---------------------------------------------------------------------------
# 2. list_zones
# ---------------------------------------------------------------------------

def list_zones(region_id: str) -> list[dict[str, Any]]:
    """List all sailing zones within a region.

    Args:
        region_id: The region identifier (e.g. ``"sf-bay"``, ``"puget-sound"``,
                   ``"sardinia"``).  Use ``list_regions`` to discover valid IDs.

    Returns a list of zone descriptors with coordinates, exposure type, known
    hazards, and flood-tide direction (where available).  Use the zone ``id``
    as ``zone_id`` in ``get_zone_forecast``, ``best_sail_windows``, and
    ``explain_score``.

    Raises ``ValueError`` if the region_id is not recognised.
    """
    region = _find_region(region_id)
    return [zone_to_dict(z) for z in region.zones]


# ---------------------------------------------------------------------------
# 3. list_profiles
# ---------------------------------------------------------------------------

def list_profiles() -> list[dict[str, Any]]:
    """List all available sailor profiles with their scoring thresholds.

    Profiles encode the experience level and boat type of the sailor, and drive
    all sailability scoring thresholds (ideal wind range, maximum gust, maximum
    wave height, minimum visibility, etc.).

    Built-in profiles: ``"school"``, ``"cruiser"`` (default), ``"racer"``.

    Returns a list of profile descriptors.  Pass the profile ``id`` as
    ``profile_id`` in forecast tools.
    """
    return [profile_to_dict(p) for p in get_all_profiles()]


# ---------------------------------------------------------------------------
# 4. get_zone_forecast
# ---------------------------------------------------------------------------

def get_zone_forecast(
    zone_id: str,
    profile_id: str = "cruiser",
    days: int = 3,
    summary: bool = True,
) -> dict[str, Any]:
    """Fetch and score the sailing forecast for a single zone.

    This is the primary forecast tool.  It fetches wind, wave, tide, and
    visibility data from live APIs, applies the sailability scoring model
    calibrated for the chosen sailor profile, and returns a structured
    forecast with:

    * ``verdict`` — human-readable go/no-go string (e.g. ``"Great sailing!"``)
    * ``current_sailability`` — 0-100 score for the next ~6 hours
    * ``best_sail_windows`` — top 3 windows with highest sustained sailability
    * ``daily`` — per-day averages for quick scanning
    * ``warnings`` — any active NOAA marine warnings (US regions only)
    * ``hourly`` — per-hour detail rows, only present when ``summary=False``

    Args:
        zone_id: Zone identifier (e.g. ``"city-front"``, ``"shilshole"``).
                 Use ``list_zones`` to discover valid IDs.
        profile_id: Sailor profile (default ``"cruiser"``). Use ``list_profiles``
                    to see all options.
        days: Number of forecast days (1–7). Default 3.
        summary: When True (default) omit per-hour rows for a compact response.
                 Set to False to include up to 72 hours of detail.

    Raises ``ValueError`` if zone_id or profile_id is not recognised.
    """
    days = max(1, min(7, days))
    region, zone = _find_zone_globally(zone_id)

    result = _svc_get_zone_forecast(
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
        profile_id=profile_id,
        cache=_cache,
    )
    return zone_forecast_to_dict(result, summary=summary)


# ---------------------------------------------------------------------------
# 5. compare_zones_in_region
# ---------------------------------------------------------------------------

def compare_zones_in_region(
    region_id: str,
    profile_id: str = "cruiser",
) -> list[dict[str, Any]]:
    """Compare all zones within a region and rank them by current sailability.

    Fetches forecasts for every zone in the region concurrently and returns
    them ranked best-to-worst by the sailability score for the next ~6 hours.

    Args:
        region_id: Region identifier (e.g. ``"sf-bay"``). Use ``list_regions``
                   to discover valid IDs.
        profile_id: Sailor profile used for scoring (default ``"cruiser"``).

    Returns a ranked list of compact zone forecast summaries, each including::

        {
          "rank": 1,
          "zone_id": "city-front",
          "zone_name": "City Front",
          "sailability": 78.5,
          "verdict": "Good sailing",
          "avg_wind_kt": 14.2,
          "max_gust_kt": 22.1,
          "avg_wave_m": 0.8,
          "has_warnings": false,
        }

    Raises ``ValueError`` if region_id or profile_id is not recognised.
    """
    region = _find_region(region_id)
    profile = _resolve_profile(profile_id)
    forecasts = get_all_zone_forecasts(region, days=3, profile=profile, cache=_cache)

    rows = []
    for rank, fc in enumerate(forecasts, start=1):
        df = fc.df_hourly
        avg_wind = _safe_float(df["wind_kt"].mean()) if "wind_kt" in df.columns else None
        max_gust = _safe_float(df["gust_kt"].max()) if "gust_kt" in df.columns else None
        avg_wave = _safe_float(df["wave_height_m"].mean()) if "wave_height_m" in df.columns else None
        rows.append({
            "rank": rank,
            "zone_id": fc.zone.id,
            "zone_name": fc.zone.name,
            "sailability": _safe_float(fc.current_sailability),
            "verdict": fc.verdict,
            "avg_wind_kt": avg_wind,
            "max_gust_kt": max_gust,
            "avg_wave_m": avg_wave,
            "has_warnings": len(fc.warnings) > 0,
        })
    return rows


# ---------------------------------------------------------------------------
# 6. best_sail_windows
# ---------------------------------------------------------------------------

def best_sail_windows(
    zone_id: str,
    profile_id: str = "cruiser",
    days: int = 3,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Find the top sailing windows (consecutive high-sailability hours) in a zone.

    Uses a 3-hour sliding-window average to identify the best sustained blocks
    of sailing conditions within the forecast period.

    Args:
        zone_id: Zone identifier. Use ``list_zones`` to discover valid IDs.
        profile_id: Sailor profile used for scoring (default ``"cruiser"``).
        days: Forecast horizon in days (1–7, default 3).
        top_n: Maximum number of windows to return (default 3).

    Returns a list of windows (at most *top_n*) sorted by score descending::

        [
          {
            "start": "2026-05-15T14:00:00",
            "end": "2026-05-15T17:00:00",
            "score": 82.4,
            "verdict": "Great sailing!"
          },
          ...
        ]

    ``verdict`` is computed from the window's average sailability score.

    Raises ``ValueError`` if zone_id or profile_id is not recognised.
    """
    from app.domain.scoring import verdict as _verdict
    days = max(1, min(7, days))
    top_n = max(1, min(10, top_n))

    forecast_dict = get_zone_forecast(zone_id=zone_id, profile_id=profile_id, days=days, summary=True)
    windows = forecast_dict.get("best_sail_windows", [])[:top_n]

    results_out = []
    for w in windows:
        score = w.get("score")
        results_out.append({
            "start": w.get("start"),
            "end": w.get("end"),
            "score": score,
            "verdict": _verdict(score) if score is not None else "Unknown",
        })
    return results_out


# ---------------------------------------------------------------------------
# 7. get_active_warnings
# ---------------------------------------------------------------------------

def get_active_warnings(region_id: str) -> list[dict[str, Any]]:
    """Return any active NOAA marine warnings for a US region.

    Only available for US regions (San Francisco Bay, Puget Sound).  Returns
    an empty list for non-US regions (Sardinia) or when no warnings are active.

    Args:
        region_id: Region identifier (e.g. ``"sf-bay"``, ``"puget-sound"``).

    Returns a list of warning dicts::

        [
          {
            "event": "Small Craft Advisory",
            "severity": "Moderate",
            "headline": "Small Craft Advisory until 8 PM PDT",
            "expires": "2026-05-15T20:00:00-07:00"
          }
        ]

    An empty list means conditions are clear (no active warnings).

    Raises ``ValueError`` if region_id is not recognised.
    """
    region = _find_region(region_id)
    if not region.nws_zone:
        return []

    try:
        raw = fetch_marine_warnings(region.nws_zone, session=None)
        return [
            {
                "event": str(w.get("event", "")),
                "severity": str(w.get("severity", "")),
                "headline": str(w.get("headline", "")),
                "expires": str(w.get("expires", "")),
            }
            for w in (raw or [])
        ]
    except Exception as exc:
        return [{"event": "error", "severity": "unknown", "headline": str(exc), "expires": ""}]


# ---------------------------------------------------------------------------
# 8. explain_score
# ---------------------------------------------------------------------------

def explain_score(
    zone_id: str,
    hour_offset: int = 0,
    profile_id: str = "cruiser",
) -> dict[str, Any]:
    """Explain the sailability score for a specific hour in a zone forecast.

    Breaks down the score into its components (wind score, sea score,
    visibility score), shows which safety gates passed or failed, and
    provides the wind-against-tide penalty value.  Returns a plain-language
    ``why_string`` summarising the main factors.

    Args:
        zone_id: Zone identifier. Use ``list_zones`` to discover valid IDs.
        hour_offset: Hour index into the forecast (0 = now, 1 = in 1 hour, …).
                     Clamped to the available forecast length.
        profile_id: Sailor profile used for scoring (default ``"cruiser"``).

    Returns::

        {
          "hour": "2026-05-15T14:00:00",
          "sailability": 78.5,
          "verdict": "Good sailing",
          "wind_score": 85.2,
          "sea_score": 70.1,
          "visibility_score": 100.0,
          "gates_passed": true,
          "wat_penalty": 0.0,
          "profile_thresholds": {
            "ideal_wind_kt": [10.0, 18.0],
            "max_gust_kt": 30.0,
            "max_wave_m": 2.5,
          },
          "why_string": "Wind 14 kt (ideal), wave 0.8 m (comfortable), visibility clear."
        }

    Raises ``ValueError`` if zone_id or profile_id is not recognised.
    """
    from app.domain.scoring import verdict as _verdict

    forecast_dict = get_zone_forecast(
        zone_id=zone_id, profile_id=profile_id, days=3, summary=False,
    )
    hourly = forecast_dict.get("hourly", [])
    if not hourly:
        raise ValueError(f"No hourly data available for zone {zone_id!r}")

    idx = max(0, min(hour_offset, len(hourly) - 1))
    row = hourly[idx]

    wind_score = row.get("wind_score")
    sea_score = row.get("sea_score")
    vis_score = row.get("visibility_score")
    sailability = row.get("sailability")
    gates_passed = row.get("gates_passed")
    wat_penalty = row.get("wat_penalty", 0.0)
    wind_kt = row.get("wind_kt")
    wave_m = row.get("wave_height_m")
    vis_m = row.get("visibility_m")

    profile_thresholds = {}
    if forecast_dict.get("profile"):
        p = forecast_dict["profile"]
        profile_thresholds = {
            "ideal_wind_kt": p.get("ideal_wind_kt"),
            "max_gust_kt": p.get("max_gust_kt"),
            "max_wave_m": p.get("max_wave_m"),
            "min_visibility_km": p.get("min_visibility_km"),
        }

    why_parts: list[str] = []
    if wind_kt is not None:
        why_parts.append(f"Wind {wind_kt:.0f} kt")
        if isinstance(profile_thresholds.get("ideal_wind_kt"), list):
            lo, hi = profile_thresholds["ideal_wind_kt"]
            if lo <= wind_kt <= hi:
                why_parts[-1] += " (ideal range)"
            elif wind_kt < lo:
                why_parts[-1] += " (light)"
            else:
                why_parts[-1] += " (strong)"
    if wave_m is not None:
        why_parts.append(f"wave {wave_m:.1f} m")
        max_wave = profile_thresholds.get("max_wave_m")
        if max_wave and wave_m > max_wave:
            why_parts[-1] += " (exceeds gate — score capped)"
        elif max_wave and wave_m > max_wave * 0.7:
            why_parts[-1] += " (rough)"
        else:
            why_parts[-1] += " (manageable)"
    if vis_m is not None:
        vis_km = vis_m / 1000.0
        min_vis = profile_thresholds.get("min_visibility_km", 1.0)
        if vis_m < (min_vis * 1000.0) if min_vis else 1000.0:
            why_parts.append(f"visibility {vis_km:.1f} km (poor — gate failed)")
        elif vis_m >= 10000.0:
            why_parts.append("visibility clear")
        else:
            why_parts.append(f"visibility {vis_km:.1f} km")
    if wat_penalty and wat_penalty > 0:
        why_parts.append(f"wind-against-tide penalty -{wat_penalty:.0f} pts")
    if gates_passed is False:
        why_parts.append("safety gate failed (score capped at 25)")

    why_string = ", ".join(why_parts) + "." if why_parts else "Insufficient data."

    return {
        "hour": row.get("time"),
        "sailability": sailability,
        "verdict": _verdict(sailability) if sailability is not None else "Unknown",
        "wind_score": wind_score,
        "sea_score": sea_score,
        "visibility_score": vis_score,
        "gates_passed": gates_passed,
        "wat_penalty": wat_penalty,
        "profile_thresholds": profile_thresholds,
        "why_string": why_string,
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _resolve_profile(profile_id: str) -> SailorProfile:
    try:
        return get_profile_by_id(profile_id)
    except Exception:
        available = ", ".join(p.id for p in get_all_profiles())
        raise ValueError(f"Unknown profile_id {profile_id!r}. Available: {available}")
