"""Streamlit page layout for California Sail — Phase 3 final.

Flow:
  1. Sidebar: region · forecast days · sailor profile
  2. Main area:
     a. Active NOAA marine warnings panel (US regions only)
     b. Zone-comparison map + ranking table
     c. Zone selectbox (defaults to best zone)
     d. Detailed forecast for selected zone (all charts + profile-aware thresholds)
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.domain.profiles import SailorProfile, get_all_profiles
from app.domain.regions import SailingRegion, load_regions
from app.services.forecast_service import ZoneForecast
from app.services.region_service import get_all_zone_forecasts
from app.ui.components import (
    error_message,
    go_nogo_header,
    hazards_section,
    last_updated_at,
    sail_windows_section,
    sailor_profile_selector,
    scoring_formula_expander,
    summary_metrics,
    warnings_panel,
)
from app.viz.charts import (
    cloud_precip_chart,
    sailability_ribbon,
    temperature_line,
    tide_curve,
    wave_height_period_bar,
    wind_against_tide_timeline,
    wind_rose,
    wind_timeline_with_gusts,
    zone_map,
)
from app.viz.themes import VERDICT_COLORS, VERDICT_EMOJI

import pandas as pd


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(
    regions: list[SailingRegion],
    profiles: list[SailorProfile],
) -> tuple[SailingRegion, int, SailorProfile]:
    """Render sidebar. Returns (region, forecast_days, profile)."""
    st.sidebar.header("Settings")

    region_names = [r.name for r in regions]
    selected_name = st.sidebar.selectbox("Sailing region", options=region_names, index=0)
    region = next(r for r in regions if r.name == selected_name)

    days = st.sidebar.slider("Forecast days", min_value=1, max_value=7, value=5)

    st.sidebar.markdown("---")
    profile = sailor_profile_selector(profiles)

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Scoring v3** — profile-driven thresholds")
    st.sidebar.caption(
        f"Gust gate: {profile.max_gust_kt:.0f} kt · "
        f"Wave gate: {profile.max_wave_m:.1f} m · "
        f"Vis gate: {profile.min_visibility_km:.0f} km"
    )

    return region, days, profile


# ---------------------------------------------------------------------------
# Zone comparison
# ---------------------------------------------------------------------------

def render_zone_comparison(results: list[ZoneForecast]) -> None:
    map_data = [
        {
            "name": r.zone.name,
            "lat": r.zone.latitude,
            "lon": r.zone.longitude,
            "sailability": r.current_sailability,
            "verdict": r.verdict,
            "exposure": r.zone.exposure,
        }
        for r in results
    ]
    st.plotly_chart(zone_map(map_data), use_container_width=True)

    st.write("")

    st.markdown("#### Zone rankings (next 6 h)")
    rows = []
    for i, r in enumerate(results):
        df24 = r.df_hourly.head(24)
        avg_wind = float(df24["wind_kt"].mean()) if not df24.empty else 0.0
        max_gust = float(df24["gust_kt"].max()) if not df24.empty and "gust_kt" in df24.columns else 0.0
        avg_wave = (
            float(df24["wave_height_m"].mean())
            if not df24.empty and "wave_height_m" in df24.columns
            else None
        )
        emoji = VERDICT_EMOJI.get(r.verdict, "❓")
        row: dict = {
            "#": i + 1,
            "Zone": r.zone.name,
            "Verdict": f"{emoji} {r.verdict}",
            "Sailability": f"{r.current_sailability:.0f}",
            "Avg wind (kt)": f"{avg_wind:.1f}",
            "Max gust (kt)": f"{max_gust:.1f}",
        }
        if avg_wave is not None:
            row["Avg wave (m)"] = f"{avg_wave:.2f}"
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Zone detail
# ---------------------------------------------------------------------------

def render_zone_detail(result: ZoneForecast) -> None:
    df = result.df_hourly
    zone = result.zone
    profile = result.profile

    # Warnings panel at the top
    if result.warnings:
        warnings_panel(result.warnings)
        st.markdown("")

    go_nogo_header(result.verdict, result.current_sailability, zone.name)

    df24 = df.head(24)
    avg_wind = float(df24["wind_kt"].mean()) if not df24.empty else 0.0
    max_gust = float(df24["gust_kt"].max()) if not df24.empty and "gust_kt" in df24.columns else 0.0
    avg_sail = float(df24["sailability"].mean()) if not df24.empty else 0.0
    summary_metrics(avg_wind, max_gust, avg_sail)

    if not df24.empty and "wave_height_m" in df24.columns:
        avg_wave = float(df24["wave_height_m"].mean())
        avg_period = float(df24["wave_period_s"].mean()) if "wave_period_s" in df24.columns else None
        avg_wat = float(df24["wat_penalty"].mean()) if "wat_penalty" in df24.columns else 0.0

        col_w, col_p, col_w2 = st.columns(3)
        col_w.metric("Avg wave height", f"{avg_wave:.2f} m")
        if avg_period is not None:
            col_p.metric("Avg wave period", f"{avg_period:.1f} s")
        if avg_wat > 2:
            col_w2.metric("WAT penalty (avg)", f"{avg_wat:.0f} pts", delta=f"−{avg_wat:.0f}", delta_color="inverse")

    hazards_section(zone.hazards)

    status_parts = []
    if result.has_marine_data:
        status_parts.append("Wave data active")
    if result.has_tide_data:
        status_parts.append("Tide & current data active")
    if status_parts:
        st.info(" · ".join(status_parts) + " — using v3 sailability scoring.")

    st.markdown("---")

    st.plotly_chart(sailability_ribbon(df, hours=72), use_container_width=True)

    col_rose, col_timeline = st.columns([1, 2])
    with col_rose:
        st.plotly_chart(wind_rose(df), use_container_width=True)
    with col_timeline:
        st.plotly_chart(wind_timeline_with_gusts(df), use_container_width=True)

    if "wave_height_m" in df.columns:
        st.plotly_chart(wave_height_period_bar(df), use_container_width=True)

    if "tide_height_m" in df.columns:
        col_tide, col_wat = st.columns([2, 1])
        with col_tide:
            st.plotly_chart(tide_curve(df), use_container_width=True)
        with col_wat:
            st.plotly_chart(wind_against_tide_timeline(df), use_container_width=True)

    col_temp, col_cloud = st.columns(2)
    with col_temp:
        st.plotly_chart(temperature_line(df), use_container_width=True)
    with col_cloud:
        st.plotly_chart(cloud_precip_chart(df), use_container_width=True)

    st.markdown("---")

    sail_windows_section(result.best_sail_windows)
    scoring_formula_expander(profile)
    last_updated_at(result.region.timezone)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(sailing_areas_path: str | Path) -> None:
    """Build full layout: sidebar → warnings → zone comparison → zone detail."""
    regions = load_regions(sailing_areas_path)
    if not regions:
        st.warning("No sailing regions configured. Check data/sailing_areas.yaml.")
        return

    profiles = get_all_profiles()
    region, days, profile = render_sidebar(regions, profiles)

    st.subheader(f"{region.name}")
    st.caption(f"{len(region.zones)} zones · {days}-day forecast · {profile.emoji} {profile.name} profile")

    with st.spinner(f"Loading forecast for all {region.name} zones…"):
        try:
            all_results = get_all_zone_forecasts(region, days=days, profile=profile)
        except Exception as e:
            error_message(str(e))
            return

    if not all_results:
        st.error("No zone forecasts could be loaded. Please check your connection.")
        return

    render_zone_comparison(all_results)

    st.markdown("---")

    zone_names = [r.zone.name for r in all_results]
    selected_zone_name = st.selectbox(
        "Select zone for detailed forecast",
        options=zone_names,
        index=0,
        help="Zones are sorted best-to-worst by current sailability.",
    )
    selected_result = next(r for r in all_results if r.zone.name == selected_zone_name)

    render_zone_detail(selected_result)
