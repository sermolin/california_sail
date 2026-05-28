"""Reusable Streamlit UI components for California Sail — Phase 3 final."""
from __future__ import annotations

import zoneinfo
from datetime import datetime

import streamlit as st

from app.viz.themes import VERDICT_COLORS, VERDICT_EMOJI

# Severity → colour for the warnings panel
_WARNING_SEVERITY_COLOR = {
    "Extreme":  "#dc3545",
    "Severe":   "#dc3545",
    "Moderate": "#fd7e14",
    "Minor":    "#ffc107",
    "Unknown":  "#6c757d",
}
_WARNING_SEVERITY_EMOJI = {
    "Extreme":  "🚨",
    "Severe":   "⛔",
    "Moderate": "⚠️",
    "Minor":    "ℹ️",
    "Unknown":  "ℹ️",
}


# ---------------------------------------------------------------------------
# Hero header
# ---------------------------------------------------------------------------

def go_nogo_header(verdict: str, sailability: float, zone_name: str) -> None:
    """Render a prominent Go/No-Go hero badge with sailability score."""
    color = VERDICT_COLORS.get(verdict, "#6c757d")
    emoji = VERDICT_EMOJI.get(verdict, "")
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {color}18, {color}30);
            border-left: 6px solid {color};
            border-radius: 8px;
            padding: 18px 24px;
            margin-bottom: 16px;
        ">
            <span style="font-size:2.2rem; font-weight:900; color:{color}; letter-spacing:-1px;">
                {emoji} {verdict}
            </span>
            &nbsp;&nbsp;
            <span style="font-size:1.1rem; color:#444;">
                {zone_name} — current sailability:
                <strong style="font-size:1.4rem; color:{color};">{sailability:.0f}</strong><span style="color:#888;">/100</span>
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Summary metrics row
# ---------------------------------------------------------------------------

def summary_metrics(
    avg_wind_kt: float,
    max_gust_kt: float,
    avg_sailability: float,
) -> None:
    """Three-column metric row."""
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Avg wind (next 24 h)", f"{avg_wind_kt:.1f} kt")
    with c2:
        st.metric("Max gust (next 24 h)", f"{max_gust_kt:.1f} kt")
    with c3:
        st.metric("Avg sailability (24 h)", f"{avg_sailability:.0f} / 100")


# ---------------------------------------------------------------------------
# Sailor profile selector
# ---------------------------------------------------------------------------

def sailor_profile_selector(profiles: list) -> "SailorProfile":  # noqa: F821
    """Render a radio selector for sailor profiles. Returns selected SailorProfile."""
    options = {f"{p.emoji} {p.name}": p for p in profiles}
    labels = list(options.keys())

    # Default to "Cruiser" if available
    default_label = next(
        (lbl for lbl in labels if "ruiser" in lbl),
        labels[0] if labels else None,
    )
    default_idx = labels.index(default_label) if default_label in labels else 0

    selected_label = st.sidebar.radio(
        "Sailor profile",
        options=labels,
        index=default_idx,
        help="Your profile adjusts all scoring thresholds (wind, wave, gust limits).",
    )
    selected = options[selected_label]

    st.sidebar.caption(f"*{selected.boat_size_hint}*")
    return selected


# ---------------------------------------------------------------------------
# Active marine warnings panel
# ---------------------------------------------------------------------------

def warnings_panel(warnings: list[dict], source: str = "noaa") -> None:
    """Display active marine warnings.  No-op if warnings is empty.

    source: "noaa"      — NOAA NWS official alerts (US regions)
            "synthetic" — derived from Open-Meteo forecast thresholds (non-US)
    """
    if not warnings:
        return

    source_label = {
        "noaa": "NOAA NWS",
        "synthetic": "Forecast-derived",
    }.get(source, source.upper())

    st.caption(f"⚡ Marine warnings · source: {source_label}")

    for w in warnings:
        sev = w.get("severity", "Unknown")
        color = _WARNING_SEVERITY_COLOR.get(sev, "#6c757d")
        icon = _WARNING_SEVERITY_EMOJI.get(sev, "ℹ️")
        event = w.get("event", "Marine Warning")
        headline = w.get("headline", "")
        expires = w.get("expires", "")
        expires_str = f"  ·  until {expires[:16].replace('T', ' ')}" if expires else ""

        st.markdown(
            f"""
            <div style="
                background-color: {color}18;
                border-left: 5px solid {color};
                border-radius: 6px;
                padding: 10px 16px;
                margin-bottom: 8px;
            ">
                <span style="font-size:1.05rem; font-weight:700; color:{color};">
                    {icon} {event}
                </span>
                <span style="font-size:0.85rem; color:#555;">{expires_str}</span>
                <br/>
                <span style="font-size:0.9rem; color:#333;">{headline}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Sailing windows section
# ---------------------------------------------------------------------------

def sail_windows_section(windows: list) -> None:
    """Render top 3-hour sailing windows."""
    if not windows:
        st.info("Not enough data to identify best sailing windows.")
        return
    st.subheader("Best 3-hour sailing windows")
    for i, (start, end, score) in enumerate(windows[:3], 1):
        color = VERDICT_COLORS["GO"] if score >= 65 else (VERDICT_COLORS["MAYBE"] if score >= 35 else VERDICT_COLORS["NO-GO"])
        st.markdown(
            f"**{i}.** `{start.strftime('%a %d %b %H:%M')}` → `{end.strftime('%H:%M')}`"
            f" &nbsp; <span style='color:{color}; font-weight:600;'>score {score:.0f}</span>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Hazards
# ---------------------------------------------------------------------------

def hazards_section(hazards: list[str]) -> None:
    """Show zone hazard tags."""
    if not hazards:
        return
    st.markdown("**Known hazards:** " + " · ".join(f"`{h}`" for h in hazards))


# ---------------------------------------------------------------------------
# Scoring formula expander (v3 — profile-aware)
# ---------------------------------------------------------------------------

def scoring_formula_expander(profile: "SailorProfile | None" = None) -> None:  # noqa: F821
    """Expander explaining the Sailability v3 formula with profile-specific thresholds."""
    from app.domain.scoring import (
        GOOD_VIS_M,
        IDEAL_WIND_SIGMA,
        WEIGHT_SEA,
        WEIGHT_VIS,
        WEIGHT_VIS_SEA,
        WEIGHT_WIND,
        WEIGHT_WIND_SEA,
        WAT_MAX_PENALTY,
    )

    if profile is None:
        from app.domain.profiles import get_default_profile
        profile = get_default_profile()

    gate_vis_km = profile.min_visibility_m / 1000.0
    ideal_mid = profile.ideal_wind_mid

    label = f"How is Sailability calculated? ({profile.emoji} {profile.name} profile)"
    with st.expander(label):
        st.markdown(f"""
**Sailability (0–100)** — *"How good is this hour for a {profile.name.lower()} sail?"*

---
**1. Hard safety gates** — if ANY gate fails, score is capped at ≤ 25:

| Gate | Threshold |
|------|-----------|
| Gust | > **{profile.max_gust_kt:.0f} kt** |
| Visibility | < **{gate_vis_km:.1f} km** |
| Wave height | > **{profile.max_wave_m:.1f} m** *(when wave data available)* |

---
**2. Component scores (0–100 each):**

- **Wind score**: Gaussian peak at **{ideal_mid:.0f} kt** (range {profile.ideal_wind_kt[0]:.0f}–{profile.ideal_wind_kt[1]:.0f} kt, σ = {IDEAL_WIND_SIGMA:.0f} kt)
- **Sea score**: 100 at flat water → 0 at {profile.max_wave_m:.1f} m. Chop penalty −{profile.chop_penalty:.0f} pts when wave period < {profile.chop_period_s:.0f} s
- **Visibility score**: 100 at ≥ {GOOD_VIS_M/1000:.0f} km → 0 at {gate_vis_km:.1f} km

---
**3. Wind-against-tide penalty** (0 – {WAT_MAX_PENALTY:.0f} pts):
Active when tidal current > {profile.wat_min_current_kt:.1f} kt and wind direction opposes current direction.

---
**4. Final sailability:**
```
With wave data:  {WEIGHT_WIND_SEA:.0%} × wind + {WEIGHT_SEA:.0%} × sea + {WEIGHT_VIS_SEA:.0%} × vis − WAT penalty
Wind/vis only:   {WEIGHT_WIND:.0%} × wind + {WEIGHT_VIS:.0%} × vis − WAT penalty
```
**Verdict**: GO ≥ 65 · MAYBE 35–64 · NO-GO < 35
        """)


# ---------------------------------------------------------------------------
# Error banner
# ---------------------------------------------------------------------------

def error_message(msg: str) -> None:
    st.error(f"Could not load forecast: {msg}")


# ---------------------------------------------------------------------------
# Last-updated timestamp (in region's local timezone)
# ---------------------------------------------------------------------------

def last_updated_at(region_timezone: str = "UTC") -> None:
    """Show a 'last updated' caption in the region's local timezone."""
    try:
        tz = zoneinfo.ZoneInfo(region_timezone)
        ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    st.caption(f"Last updated: {ts}")
