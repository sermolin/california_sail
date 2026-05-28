"""Synthesise marine warnings from an hourly forecast DataFrame.

Used for non-NOAA regions (e.g. Sardinia) where no official alert feed is
available.  Thresholds follow WMO/IMO Beaufort-scale equivalents and the
Italian/Mediterranean meteorological service conventions:

  Strong Wind Warning   wind ≥ 22 kt  OR gust ≥ 28 kt   (BF 6–7)
  Gale Warning          wind ≥ 34 kt  OR gust ≥ 40 kt   (BF 8–9)
  Storm Warning         wind ≥ 48 kt  OR gust ≥ 55 kt   (BF 10+)
  Rough Sea Warning     wave ≥ 2.5 m
  Very Rough Sea        wave ≥ 4.0 m
  Dense Fog Advisory    visibility < 1 000 m

Only the next 24 hours of the DataFrame are examined.  The `expires` field is
set to the ISO timestamp of the last hour where the condition holds, so the
caller gets a realistic expiry window rather than a static offset.

Output dicts share the same keys as the NOAA client so the rest of the app
(serializers, UI, formatters) needs no changes:
  event, severity, urgency, headline, description, effective, expires, status
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

_log = logging.getLogger(__name__)

# Severity → sort order (lower = worse, mirrors noaa_warnings_client)
_SEVERITY_ORDER = {
    "Extreme": 0,
    "Severe": 1,
    "Moderate": 2,
    "Minor": 3,
    "Unknown": 4,
}

# Columns that must be present for each check
_WIND_COLS = {"wind_kt", "gust_kt"}
_WAVE_COLS = {"wave_height_m"}
_VIS_COLS = {"visibility_m"}


def _last_active_hour(series: "pd.Series[bool]", timestamps: "pd.Series") -> str:
    """Return ISO timestamp of the last True entry, or empty string."""
    active = timestamps[series]
    if active.empty:
        return ""
    last = active.iloc[-1]
    if hasattr(last, "isoformat"):
        return last.isoformat()
    return str(last)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def synthesize_warnings(df_hourly: pd.DataFrame) -> list[dict]:
    """Return a list of active marine warnings derived from *df_hourly*.

    Examines the first 24 rows (hours).  Returns `[]` when the DataFrame is
    empty or no threshold is exceeded.  Never raises — all errors are logged
    and swallowed so the forecast path degrades gracefully.
    """
    if df_hourly is None or df_hourly.empty:
        return []

    try:
        return _synthesize(df_hourly)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Warning synthesis failed: %s", exc)
        return []


def _synthesize(df: pd.DataFrame) -> list[dict]:
    window = df.head(24).copy()
    ts_col = "timestamp" if "timestamp" in window.columns else None

    def _ts(mask: "pd.Series[bool]") -> str:
        if ts_col is None:
            return ""
        return _last_active_hour(mask, window[ts_col])

    now = _now_iso()
    warnings: list[dict] = []

    has_wind = _WIND_COLS.issubset(window.columns)
    has_wave = _WAVE_COLS.issubset(window.columns)
    has_vis = _VIS_COLS.issubset(window.columns)

    if has_wind:
        wind = window["wind_kt"]
        gust = window["gust_kt"]

        # Storm Warning (BF 10+)
        storm_mask = (wind >= 48) | (gust >= 55)
        if storm_mask.any():
            max_wind = float(wind[storm_mask].max())
            max_gust = float(gust[storm_mask].max())
            warnings.append({
                "event": "Storm Warning",
                "severity": "Severe",
                "urgency": "Immediate",
                "headline": (
                    f"Storm Warning: wind up to {max_wind:.0f} kt, "
                    f"gusts up to {max_gust:.0f} kt — dangerous for all vessels"
                ),
                "description": (
                    "Extremely dangerous conditions. All vessels should seek shelter "
                    "immediately. Do not enter open water."
                ),
                "effective": now,
                "expires": _ts(storm_mask),
                "status": "Actual",
            })

        # Gale Warning (BF 8–9), only if Storm not already issued
        elif (gale_mask := (wind >= 34) | (gust >= 40)).any():
            max_wind = float(wind[gale_mask].max())
            max_gust = float(gust[gale_mask].max())
            warnings.append({
                "event": "Gale Warning",
                "severity": "Severe",
                "urgency": "Expected",
                "headline": (
                    f"Gale Warning: wind up to {max_wind:.0f} kt, "
                    f"gusts up to {max_gust:.0f} kt"
                ),
                "description": (
                    "Gale-force winds expected. Small craft and recreational vessels "
                    "should remain in harbour."
                ),
                "effective": now,
                "expires": _ts(gale_mask),
                "status": "Actual",
            })

        # Strong Wind Warning (BF 6–7), only if no higher warning already issued
        elif (strong_mask := (wind >= 22) | (gust >= 28)).any():
            max_wind = float(wind[strong_mask].max())
            max_gust = float(gust[strong_mask].max())
            warnings.append({
                "event": "Strong Wind Warning",
                "severity": "Moderate",
                "urgency": "Expected",
                "headline": (
                    f"Strong Wind Warning: wind up to {max_wind:.0f} kt, "
                    f"gusts up to {max_gust:.0f} kt"
                ),
                "description": (
                    "Strong winds expected. Inexperienced sailors and small craft "
                    "should exercise caution."
                ),
                "effective": now,
                "expires": _ts(strong_mask),
                "status": "Actual",
            })

    if has_wave:
        wave = window["wave_height_m"]

        # Very Rough Sea (wave ≥ 4 m)
        vrough_mask = wave >= 4.0
        if vrough_mask.any():
            max_wave = float(wave[vrough_mask].max())
            warnings.append({
                "event": "Very Rough Sea Warning",
                "severity": "Severe",
                "urgency": "Expected",
                "headline": f"Very Rough Sea Warning: waves up to {max_wave:.1f} m",
                "description": (
                    "Very rough seas (≥ 4 m). Navigation extremely hazardous "
                    "for recreational craft."
                ),
                "effective": now,
                "expires": _ts(vrough_mask),
                "status": "Actual",
            })

        # Rough Sea (wave ≥ 2.5 m), only if Very Rough not already issued
        elif (rough_mask := wave >= 2.5).any():
            max_wave = float(wave[rough_mask].max())
            warnings.append({
                "event": "Rough Sea Warning",
                "severity": "Moderate",
                "urgency": "Expected",
                "headline": f"Rough Sea Warning: waves up to {max_wave:.1f} m",
                "description": (
                    "Rough sea conditions (≥ 2.5 m). Small craft and beginner sailors "
                    "should avoid open water."
                ),
                "effective": now,
                "expires": _ts(rough_mask),
                "status": "Actual",
            })

    if has_vis:
        vis = window["visibility_m"]
        fog_mask = vis < 1000
        if fog_mask.any():
            min_vis = float(vis[fog_mask].min())
            warnings.append({
                "event": "Dense Fog Advisory",
                "severity": "Minor",
                "urgency": "Expected",
                "headline": f"Dense Fog Advisory: visibility down to {min_vis/1000:.1f} km",
                "description": (
                    "Dense fog reducing visibility below 1 km. Navigate with caution "
                    "and use sound signals."
                ),
                "effective": now,
                "expires": _ts(fog_mask),
                "status": "Actual",
            })

    warnings.sort(key=lambda w: _SEVERITY_ORDER.get(w["severity"], 99))
    return warnings
