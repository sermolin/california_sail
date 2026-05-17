"""Shared Plotly layout defaults and color scales."""
from __future__ import annotations

LAYOUT_DEFAULTS: dict = {
    "margin": {"l": 40, "r": 20, "t": 50, "b": 40},
    "height": 340,
    "showlegend": True,
    "plot_bgcolor": "rgba(0,0,0,0)",
    "paper_bgcolor": "rgba(0,0,0,0)",
}

# Sailability color scale: red (0) → amber (50) → green (100)
SAILABILITY_COLORSCALE = [
    [0.0,  "rgb(220, 53, 69)"],    # No-Go  — red
    [0.35, "rgb(220, 53, 69)"],
    [0.35, "rgb(255, 193, 7)"],    # Maybe  — amber
    [0.65, "rgb(255, 193, 7)"],
    [0.65, "rgb(40, 167, 69)"],    # Go     — green
    [1.0,  "rgb(40, 167, 69)"],
]

# Discrete verdict colours
VERDICT_COLORS = {
    "GO": "#28a745",
    "MAYBE": "#ffc107",
    "NO-GO": "#dc3545",
}

VERDICT_EMOJI = {
    "GO": "✅",
    "MAYBE": "⚠️",
    "NO-GO": "🚫",
}
