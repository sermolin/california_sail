"""Sailability score (v1) — vectorized, fully explainable.

Phase 1 hardcodes a cruiser-style baseline profile. Phase 3 will accept a
SailorProfile dataclass so all thresholds become user-selectable.

Sailability (0–100) answers: "How good is this hour for a relaxed cruising sail?"

Formula
-------
1. Hard safety gates (any failure caps score at ≤ 25 and sets gates_passed=False):
     - gust_kt > GATE_GUST_KT       (default: 30 kt)
     - visibility_m < GATE_VIS_M    (default: 1 000 m)

2. wind_score (0–100):
     Gaussian centred on the midpoint of IDEAL_WIND_KT range.
     Peaks at 100 when wind == midpoint, decays symmetrically outside the range.

3. visibility_score (0–100):
     100 when visibility ≥ GOOD_VIS_M (10 000 m), linear decay to 0 below GATE_VIS_M.

4. Final sailability = weighted average:
     sailability = 0.55 × wind_score + 0.45 × visibility_score
     If gates_passed is False:  sailability = min(sailability, 25).

Additional columns added to the DataFrame:
    gates_passed    bool
    wind_score      float 0–100
    visibility_score float 0–100
    sailability     float 0–100
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Baseline cruiser profile constants (Phase 1 hardcoded; Phase 3 parameterises)
# ---------------------------------------------------------------------------

IDEAL_WIND_KT: tuple[float, float] = (10.0, 18.0)   # sweet-spot range
IDEAL_WIND_MID: float = (IDEAL_WIND_KT[0] + IDEAL_WIND_KT[1]) / 2.0
IDEAL_WIND_SIGMA: float = 8.0          # std-dev for Gaussian wind scoring

GATE_GUST_KT: float = 30.0             # hard no-go gust threshold
GATE_VIS_M: float = 1_000.0            # hard no-go visibility threshold (1 km)
GOOD_VIS_M: float = 10_000.0           # visibility at which score = 100

WEIGHT_WIND: float = 0.55
WEIGHT_VIS: float = 0.45

# Safety cap when any gate fails
GATE_SCORE_CAP: float = 25.0


def _wind_score(wind_kt: "np.ndarray | pd.Series") -> "np.ndarray":
    """Gaussian-shaped wind score centred on IDEAL_WIND_MID."""
    arr = np.asarray(wind_kt, dtype=float)
    raw = 100.0 * np.exp(-0.5 * ((arr - IDEAL_WIND_MID) / IDEAL_WIND_SIGMA) ** 2)
    return np.clip(raw, 0.0, 100.0)


def _visibility_score(vis_m: "np.ndarray | pd.Series") -> "np.ndarray":
    """Linear score: 100 at GOOD_VIS_M, 0 at GATE_VIS_M."""
    arr = np.asarray(vis_m, dtype=float)
    span = GOOD_VIS_M - GATE_VIS_M
    raw = (arr - GATE_VIS_M) / span * 100.0
    return np.clip(raw, 0.0, 100.0)


def add_sailability_to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Add sailability columns to an hourly DataFrame.

    Expects columns: wind_kt, gust_kt, visibility_m
    Adds:            wind_score, visibility_score, gates_passed, sailability
    """
    if df.empty:
        for col in ("wind_score", "visibility_score", "gates_passed", "sailability"):
            df = df.copy()
            df[col] = pd.Series(dtype=float if col != "gates_passed" else bool)
        return df

    out = df.copy()

    wind_kt = out["wind_kt"].fillna(0.0).to_numpy(dtype=float)
    gust_kt = out["gust_kt"].fillna(0.0).to_numpy(dtype=float)
    vis_m = out["visibility_m"].fillna(GOOD_VIS_M).to_numpy(dtype=float)

    ws = _wind_score(wind_kt)
    vs = _visibility_score(vis_m)
    gates = (gust_kt <= GATE_GUST_KT) & (vis_m >= GATE_VIS_M)

    raw_score = WEIGHT_WIND * ws + WEIGHT_VIS * vs
    sailability = np.where(gates, raw_score, np.minimum(raw_score, GATE_SCORE_CAP))
    sailability = np.clip(sailability, 0.0, 100.0)

    out["wind_score"] = ws
    out["visibility_score"] = vs
    out["gates_passed"] = gates
    out["sailability"] = sailability
    return out


def best_windows(
    df_hourly: pd.DataFrame,
    window_hours: int = 3,
    top_n: int = 3,
) -> list[tuple[pd.Timestamp, pd.Timestamp, float]]:
    """Return the top N consecutive windows ranked by average sailability.

    Returns list of (start_timestamp, end_timestamp, avg_sailability).
    Requires columns: timestamp, sailability.
    """
    if df_hourly.empty or len(df_hourly) < window_hours:
        return []
    if "timestamp" not in df_hourly.columns or "sailability" not in df_hourly.columns:
        return []

    df = df_hourly.sort_values("timestamp").reset_index(drop=True)
    windows: list[tuple[pd.Timestamp, pd.Timestamp, float]] = []
    for i in range(len(df) - window_hours + 1):
        chunk = df.iloc[i : i + window_hours]
        avg = float(chunk["sailability"].mean())
        windows.append((chunk["timestamp"].iloc[0], chunk["timestamp"].iloc[-1], avg))

    windows.sort(key=lambda x: -x[2])
    return windows[:top_n]


def daily_sailability_avg(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hourly sailability by date. Returns date + sailability_avg."""
    if (
        df_hourly.empty
        or "timestamp" not in df_hourly.columns
        or "sailability" not in df_hourly.columns
    ):
        return pd.DataFrame(columns=["date", "sailability_avg"])

    df = df_hourly.copy()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.normalize()
    agg = df.groupby("date", as_index=False)["sailability"].mean()
    return agg.rename(columns={"sailability": "sailability_avg"})


def verdict(sailability: float) -> str:
    """Return a Go/Maybe/No-Go verdict string from an average sailability score."""
    if sailability >= 65:
        return "GO"
    if sailability >= 35:
        return "MAYBE"
    return "NO-GO"
