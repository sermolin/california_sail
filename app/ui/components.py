"""Reusable Streamlit UI components for California Sail."""
from __future__ import annotations

import streamlit as st

from app.viz.themes import VERDICT_COLORS, VERDICT_EMOJI


def go_nogo_header(verdict: str, sailability: float, zone_name: str) -> None:
    """Render a prominent Go/No-Go header with sailability score."""
    color = VERDICT_COLORS.get(verdict, "#6c757d")
    emoji = VERDICT_EMOJI.get(verdict, "")
    st.markdown(
        f"""
        <div style="
            background-color: {color}22;
            border-left: 6px solid {color};
            border-radius: 6px;
            padding: 16px 20px;
            margin-bottom: 16px;
        ">
            <span style="font-size:2rem; font-weight:800; color:{color};">
                {emoji} {verdict}
            </span>
            &nbsp;&nbsp;
            <span style="font-size:1.1rem; color:#333;">
                {zone_name} — current sailability score: <strong>{sailability:.0f}/100</strong>
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


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


def hazards_section(hazards: list[str]) -> None:
    """Show zone hazard tags."""
    if not hazards:
        return
    st.markdown("**Known hazards:** " + " · ".join(f"`{h}`" for h in hazards))


def scoring_formula_expander() -> None:
    """Expander explaining the Sailability v1 formula."""
    from app.domain.scoring import (
        GATE_GUST_KT,
        GATE_VIS_M,
        GOOD_VIS_M,
        IDEAL_WIND_KT,
        IDEAL_WIND_SIGMA,
        WEIGHT_VIS,
        WEIGHT_WIND,
    )
    with st.expander("How is the Sailability score calculated? (Phase 1 — cruiser baseline)"):
        st.markdown(f"""
**Sailability (0–100)** answers: *"How good is this hour for a relaxed cruising sail?"*

**1. Hard safety gates** — if ANY gate fails, score is capped at ≤ 25:
- Gust > **{GATE_GUST_KT:.0f} kt** → No-Go gate
- Visibility < **{GATE_VIS_M/1000:.0f} km** → No-Go gate

**2. Wind score (0–100):**
- Gaussian peak centred on **{(IDEAL_WIND_KT[0]+IDEAL_WIND_KT[1])/2:.0f} kt**
  (sweet spot range {IDEAL_WIND_KT[0]:.0f}–{IDEAL_WIND_KT[1]:.0f} kt, σ = {IDEAL_WIND_SIGMA:.0f} kt)

**3. Visibility score (0–100):**
- Linear: 100 at ≥ {GOOD_VIS_M/1000:.0f} km, 0 at {GATE_VIS_M/1000:.0f} km

**Final sailability:**
```
sailability = {WEIGHT_WIND:.0%} × wind_score + {WEIGHT_VIS:.0%} × visibility_score
(capped at 25 if any gate fails)
```

*Phase 2 will add sea state (waves + chop) and wind-against-tide penalty.*
*Phase 3 will let you choose a sailor profile (school / cruiser / racer) to adjust all thresholds.*
        """)


def error_message(msg: str) -> None:
    """Friendly error banner."""
    st.error(f"Could not load forecast: {msg}")


def last_updated_at(ts: str) -> None:
    """Timestamp caption."""
    st.caption(f"Last updated: {ts}")
