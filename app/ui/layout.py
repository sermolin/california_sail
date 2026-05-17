"""Streamlit page layout for California Sail."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from app.domain.regions import SailingRegion, load_regions
from app.services.forecast_service import ZoneForecast, get_default_zone_forecast
from app.ui.components import (
    error_message,
    go_nogo_header,
    hazards_section,
    last_updated_at,
    sail_windows_section,
    scoring_formula_expander,
    summary_metrics,
)
from app.viz.charts import (
    cloud_precip_chart,
    sailability_ribbon,
    temperature_line,
    wind_rose,
    wind_timeline_with_gusts,
)


def render_sidebar(regions: list[SailingRegion]) -> tuple[SailingRegion, int]:
    """Render sidebar controls. Returns (selected_region, forecast_days)."""
    st.sidebar.header("Settings")

    region_names = [r.name for r in regions]
    selected_name = st.sidebar.selectbox("Sailing region", options=region_names, index=0)
    region = next(r for r in regions if r.name == selected_name)

    days = st.sidebar.slider("Forecast days", min_value=1, max_value=7, value=5)

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Scoring profile (Phase 1)**")
    st.sidebar.info(
        "Cruiser baseline — ideal wind 10–18 kt, gust gate 30 kt.\n\n"
        "Phase 3 will add School / Cruiser / Racer profiles."
    )

    return region, days


def render_zone_detail(result: ZoneForecast) -> None:
    """Render full forecast detail for a zone."""
    df = result.df_hourly
    zone = result.zone

    # --- Hero header ---
    go_nogo_header(result.verdict, result.current_sailability, zone.name)

    # --- Summary metrics (next 24 h) ---
    df24 = df.head(24)
    avg_wind = float(df24["wind_kt"].mean()) if not df24.empty else 0.0
    max_gust = float(df24["gust_kt"].max()) if not df24.empty and "gust_kt" in df24.columns else 0.0
    avg_sail = float(df24["sailability"].mean()) if not df24.empty else 0.0
    summary_metrics(avg_wind, max_gust, avg_sail)

    # --- Hazards ---
    hazards_section(zone.hazards)

    st.markdown("---")

    # --- Sailability ribbon ---
    st.plotly_chart(sailability_ribbon(df, hours=72), use_container_width=True)

    # --- Wind charts ---
    col_rose, col_timeline = st.columns([1, 2])
    with col_rose:
        st.plotly_chart(wind_rose(df), use_container_width=True)
    with col_timeline:
        st.plotly_chart(wind_timeline_with_gusts(df), use_container_width=True)

    # --- Secondary charts ---
    col_temp, col_cloud = st.columns(2)
    with col_temp:
        st.plotly_chart(temperature_line(df), use_container_width=True)
    with col_cloud:
        st.plotly_chart(cloud_precip_chart(df), use_container_width=True)

    st.markdown("---")

    # --- Best windows ---
    sail_windows_section(result.best_sail_windows)

    # --- Scoring formula ---
    scoring_formula_expander()

    # --- Timestamp ---
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    last_updated_at(ts)


def run(sailing_areas_path: str | Path) -> None:
    """Build full layout: load regions, sidebar, main area."""
    regions = load_regions(sailing_areas_path)
    if not regions:
        st.warning("No sailing regions configured. Check data/sailing_areas.yaml.")
        return

    region, days = render_sidebar(regions)

    st.subheader(f"{region.name} — {region.zones[0].name}")

    with st.spinner(f"Loading forecast for {region.zones[0].name}…"):
        try:
            result = get_default_zone_forecast(region, days=days)
        except Exception as e:
            error_message(str(e))
            return

    render_zone_detail(result)
