"""Plotly chart builders for California Sail (Phase 1 + Phase 2).

Each function is pure: DataFrame → go.Figure.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.graph_objects import Figure

from app.viz.themes import LAYOUT_DEFAULTS, SAILABILITY_COLORSCALE


# ---------------------------------------------------------------------------
# Sailability ribbon
# ---------------------------------------------------------------------------

def sailability_ribbon(df_hourly: pd.DataFrame, hours: int = 72) -> Figure:
    """72-hour at-a-glance Go/No-Go heatmap (single row, coloured by sailability).

    Red (0) → amber (50) → green (100).
    """
    if df_hourly.empty or "sailability" not in df_hourly.columns:
        return go.Figure(layout=go.Layout(**LAYOUT_DEFAULTS, title="Sailability (next 72 h)"))

    df = df_hourly.head(hours).copy()
    timestamps = df["timestamp"].astype(str).tolist()
    scores = df["sailability"].fillna(0.0).tolist()

    ribbon_layout = {**LAYOUT_DEFAULTS, "height": 160}
    fig = go.Figure(
        data=go.Heatmap(
            z=[scores],
            x=timestamps,
            y=["Sailability"],
            colorscale=SAILABILITY_COLORSCALE,
            zmin=0,
            zmax=100,
            colorbar=dict(title="Score", thickness=12),
            hovertemplate="%{x}<br>Sailability: %{z:.0f}<extra></extra>",
        ),
        layout=go.Layout(
            **ribbon_layout,
            title="Sailability ribbon — next 72 hours",
            xaxis_title="Time",
        ),
    )
    return fig


# ---------------------------------------------------------------------------
# Wind rose
# ---------------------------------------------------------------------------

def wind_rose(df_hourly: pd.DataFrame) -> Figure:
    """Polar bar chart of wind speed distribution by direction.

    Directions are binned into 16 compass sectors.
    Two traces: mean wind speed and gust speed.
    """
    if (
        df_hourly.empty
        or "wind_kt" not in df_hourly.columns
        or "wind_dir_deg" not in df_hourly.columns
    ):
        return go.Figure(layout=go.Layout(**LAYOUT_DEFAULTS, title="Wind rose"))

    df = df_hourly.dropna(subset=["wind_kt", "wind_dir_deg"]).copy()
    if df.empty:
        return go.Figure(layout=go.Layout(**LAYOUT_DEFAULTS, title="Wind rose"))

    # Bin into 16 sectors (22.5° each)
    sector_labels = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    n_sectors = 16
    sector_width = 360.0 / n_sectors
    df["sector"] = ((df["wind_dir_deg"] + sector_width / 2) % 360 // sector_width).astype(int)

    wind_by_sector = df.groupby("sector")["wind_kt"].mean().reindex(range(n_sectors), fill_value=0.0)
    labels = [sector_labels[i] for i in range(n_sectors)]

    traces = [
        go.Barpolar(
            r=wind_by_sector.values,
            theta=labels,
            name="Avg wind (kt)",
            marker_color="steelblue",
            opacity=0.85,
        )
    ]

    if "gust_kt" in df.columns:
        gust_by_sector = df.groupby("sector")["gust_kt"].mean().reindex(range(n_sectors), fill_value=0.0)
        traces.append(
            go.Barpolar(
                r=gust_by_sector.values,
                theta=labels,
                name="Avg gust (kt)",
                marker_color="tomato",
                opacity=0.5,
            )
        )

    layout = go.Layout(
        **{k: v for k, v in LAYOUT_DEFAULTS.items() if k != "height"},
        height=400,
        title="Wind rose — direction & speed distribution",
        polar=dict(
            radialaxis=dict(visible=True, title="kt"),
            angularaxis=dict(direction="clockwise", rotation=90),
        ),
    )
    return go.Figure(data=traces, layout=layout)


# ---------------------------------------------------------------------------
# Wind timeline with gust ribbon
# ---------------------------------------------------------------------------

def wind_timeline_with_gusts(df_hourly: pd.DataFrame) -> Figure:
    """Line chart of mean wind speed with a shaded gust band.

    Background bands tinted by sailability bucket (green / amber / red).
    """
    if df_hourly.empty or "wind_kt" not in df_hourly.columns:
        return go.Figure(layout=go.Layout(**LAYOUT_DEFAULTS, title="Wind forecast"))

    df = df_hourly.copy()
    ts = df["timestamp"].astype(str)

    fig = go.Figure(
        layout=go.Layout(
            **LAYOUT_DEFAULTS,
            title="Wind speed & gusts forecast",
            xaxis_title="Time",
            yaxis_title="Knots",
            yaxis=dict(rangemode="tozero"),
        )
    )

    # Gust fill band (gust – wind)
    if "gust_kt" in df.columns:
        fig.add_trace(go.Scatter(
            x=ts.tolist() + ts.tolist()[::-1],
            y=df["gust_kt"].tolist() + df["wind_kt"].tolist()[::-1],
            fill="toself",
            fillcolor="rgba(220,53,69,0.15)",
            line=dict(color="rgba(255,255,255,0)"),
            name="Gust band",
            showlegend=True,
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=ts,
            y=df["gust_kt"],
            mode="lines",
            line=dict(color="tomato", dash="dot", width=1.5),
            name="Gust (kt)",
        ))

    fig.add_trace(go.Scatter(
        x=ts,
        y=df["wind_kt"],
        mode="lines+markers",
        line=dict(color="steelblue", width=2),
        marker=dict(size=4),
        name="Wind (kt)",
    ))

    # Horizontal reference lines for profile thresholds
    from app.domain.scoring import IDEAL_WIND_KT, GATE_GUST_KT
    fig.add_hline(
        y=IDEAL_WIND_KT[0], line_dash="dash",
        line_color="rgba(40,167,69,0.5)",
        annotation_text=f"Ideal low ({IDEAL_WIND_KT[0]:.0f} kt)", annotation_position="top right",
    )
    fig.add_hline(
        y=IDEAL_WIND_KT[1], line_dash="dash",
        line_color="rgba(40,167,69,0.5)",
        annotation_text=f"Ideal high ({IDEAL_WIND_KT[1]:.0f} kt)", annotation_position="top right",
    )
    fig.add_hline(
        y=GATE_GUST_KT, line_dash="solid",
        line_color="rgba(220,53,69,0.7)",
        annotation_text=f"Gust gate ({GATE_GUST_KT:.0f} kt)", annotation_position="top right",
    )

    return fig


# ---------------------------------------------------------------------------
# Temperature line (secondary detail chart)
# ---------------------------------------------------------------------------

def temperature_line(df_hourly: pd.DataFrame) -> Figure:
    """Simple hourly air temperature line chart."""
    if df_hourly.empty or "temp_c" not in df_hourly.columns:
        return go.Figure(layout=go.Layout(**LAYOUT_DEFAULTS, title="Air temperature"))

    fig = go.Figure(
        data=go.Scatter(
            x=df_hourly["timestamp"].astype(str),
            y=df_hourly["temp_c"],
            mode="lines",
            line=dict(color="darkorange", width=2),
            name="Temp (°C)",
        ),
        layout=go.Layout(
            **LAYOUT_DEFAULTS,
            title="Air temperature (°C)",
            xaxis_title="Time",
            yaxis_title="°C",
        ),
    )
    return fig


# ---------------------------------------------------------------------------
# Cloud cover + precipitation bar
# ---------------------------------------------------------------------------

def cloud_precip_chart(df_hourly: pd.DataFrame) -> Figure:
    """Dual-axis: cloud cover line + precipitation bars."""
    if df_hourly.empty:
        return go.Figure(layout=go.Layout(**LAYOUT_DEFAULTS, title="Cloud cover & precipitation"))

    fig = go.Figure(
        layout=go.Layout(
            **LAYOUT_DEFAULTS,
            title="Cloud cover & precipitation",
            xaxis_title="Time",
            yaxis=dict(title="Cloud cover (%)", range=[0, 100]),
            yaxis2=dict(title="Precip (mm)", overlaying="y", side="right", showgrid=False),
        )
    )
    ts = df_hourly["timestamp"].astype(str)

    if "cloud_pct" in df_hourly.columns:
        fig.add_trace(go.Scatter(
            x=ts, y=df_hourly["cloud_pct"],
            mode="lines", name="Cloud (%)",
            line=dict(color="slategray", width=1.5),
            yaxis="y",
        ))
    if "precip_mm" in df_hourly.columns:
        fig.add_trace(go.Bar(
            x=ts, y=df_hourly["precip_mm"],
            name="Precip (mm)",
            marker_color="royalblue",
            opacity=0.6,
            yaxis="y2",
        ))
    return fig


# ---------------------------------------------------------------------------
# Phase 2 charts
# ---------------------------------------------------------------------------

def wave_height_period_bar(df_hourly: pd.DataFrame) -> Figure:
    """Bar chart of wave height coloured by wave period (short period = chop = warm colour)."""
    if df_hourly.empty or "wave_height_m" not in df_hourly.columns:
        return go.Figure(layout=go.Layout(**LAYOUT_DEFAULTS, title="Wave height & period"))

    df = df_hourly.copy()
    ts = df["timestamp"].astype(str)
    heights = df["wave_height_m"].fillna(0.0)
    periods = df["wave_period_s"].fillna(8.0) if "wave_period_s" in df.columns else [8.0] * len(df)

    # Map wave period to a colour: short period (chop) → tomato, long swell → steelblue
    def _period_color(p: float) -> str:
        if p < 4.0:
            return "tomato"
        if p < 7.0:
            return "goldenrod"
        return "steelblue"

    colors = [_period_color(float(p)) for p in periods]

    fig = go.Figure(
        data=go.Bar(
            x=ts,
            y=heights,
            marker_color=colors,
            name="Wave height (m)",
            hovertemplate="%{x}<br>Height: %{y:.2f} m<extra></extra>",
        ),
        layout=go.Layout(
            **LAYOUT_DEFAULTS,
            title="Wave height (colour = period: blue=swell, red=chop)",
            xaxis_title="Time",
            yaxis_title="Wave height (m)",
        ),
    )

    # Gate line
    from app.domain.scoring import GATE_WAVE_M
    fig.add_hline(
        y=GATE_WAVE_M, line_dash="solid",
        line_color="rgba(220,53,69,0.7)",
        annotation_text=f"Gate ({GATE_WAVE_M:.1f} m)", annotation_position="top right",
    )
    return fig


def tide_curve(df_hourly: pd.DataFrame) -> Figure:
    """Tide water-level curve with flood/ebb shading and current speed overlay."""
    if df_hourly.empty or "tide_height_m" not in df_hourly.columns:
        return go.Figure(layout=go.Layout(**LAYOUT_DEFAULTS, title="Tide & currents"))

    df = df_hourly.copy()
    ts = df["timestamp"].astype(str)
    heights = df["tide_height_m"].ffill()

    fig = go.Figure(
        layout=go.Layout(
            **LAYOUT_DEFAULTS,
            title="Tide height & tidal current speed",
            xaxis_title="Time",
            yaxis=dict(title="Tide height (m MLLW)"),
            yaxis2=dict(title="Current speed (kt)", overlaying="y", side="right", showgrid=False),
        )
    )

    fig.add_trace(go.Scatter(
        x=ts, y=heights,
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(100,149,237,0.2)",
        line=dict(color="cornflowerblue", width=2),
        name="Tide height (m)",
        yaxis="y",
    ))

    if "current_speed_kt" in df.columns:
        fig.add_trace(go.Scatter(
            x=ts, y=df["current_speed_kt"].fillna(0.0),
            mode="lines",
            line=dict(color="darkorange", width=1.5, dash="dot"),
            name="Current (kt, approx)",
            yaxis="y2",
        ))

    return fig


def wind_against_tide_timeline(df_hourly: pd.DataFrame) -> Figure:
    """Binary warning timeline: red when wind-against-tide penalty is active."""
    if df_hourly.empty or "wat_penalty" not in df_hourly.columns:
        return go.Figure(layout=go.Layout(
            **{**LAYOUT_DEFAULTS, "height": 120},
            title="Wind-against-tide warning",
        ))

    df = df_hourly.copy()
    ts = df["timestamp"].astype(str)
    wat = df["wat_penalty"].fillna(0.0)

    fig = go.Figure(
        layout=go.Layout(
            **{**LAYOUT_DEFAULTS, "height": 120},
            title="Wind-against-tide penalty (active = red)",
            xaxis_title="Time",
            yaxis=dict(title="Penalty (pts)", range=[0, 30]),
        )
    )
    # Colour each bar independently
    colors = ["rgba(220,53,69,0.7)" if v > 5 else "rgba(40,167,69,0.3)" for v in wat]
    fig.add_trace(go.Bar(
        x=ts, y=wat,
        marker_color=colors,
        name="WAT penalty",
        hovertemplate="%{x}<br>Penalty: %{y:.0f} pts<extra></extra>",
    ))
    return fig


def zone_map(
    zones_data: list[dict],
) -> Figure:
    """Scattermapbox of sailing zones coloured and sized by current sailability.

    zones_data: list of dicts with keys:
        name, lat, lon, sailability, verdict, exposure
    """
    if not zones_data:
        return go.Figure()

    lats = [z["lat"] for z in zones_data]
    lons = [z["lon"] for z in zones_data]
    names = [z["name"] for z in zones_data]
    scores = [z.get("sailability", 50.0) for z in zones_data]
    verdicts = [z.get("verdict", "MAYBE") for z in zones_data]

    from app.viz.themes import VERDICT_COLORS
    marker_colors = [VERDICT_COLORS.get(v, "#6c757d") for v in verdicts]
    texts = [
        f"<b>{n}</b><br>Sailability: {s:.0f}<br>{v}"
        for n, s, v in zip(names, scores, verdicts)
    ]

    fig = go.Figure(
        data=go.Scattermap(
            lat=lats,
            lon=lons,
            mode="markers+text",
            marker=go.scattermap.Marker(
                size=18,
                color=marker_colors,
                opacity=0.9,
            ),
            text=[f"{n}<br>{s:.0f}" for n, s in zip(names, scores)],
            textposition="top right",
            hovertext=texts,
            hoverinfo="text",
            name="Zones",
        ),
        layout=go.Layout(
            map=dict(
                style="open-street-map",
                center=dict(lat=sum(lats) / len(lats), lon=sum(lons) / len(lons)),
                zoom=8,
            ),
            margin=dict(l=0, r=0, t=40, b=40),
            height=420,
            title="Zone comparison — current sailability",
            showlegend=False,
        ),
    )
    return fig
