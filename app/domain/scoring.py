"""Sailability score (v2) — vectorized, fully explainable.

v2 adds sea-state scoring (wave height + chop penalty) and a wind-against-tide
penalty on top of the v1 wind + visibility formula. All new columns are optional:
if marine / tide data is absent the function gracefully falls back to v1 behaviour.

Phase 3 will replace hardcoded thresholds with a SailorProfile dataclass.

Formula
-------
1. Hard safety gates (any failure → score capped at ≤ 25, gates_passed = False):
     - gust_kt       > GATE_GUST_KT   (30 kt)
     - visibility_m  < GATE_VIS_M     (1 000 m)
     - wave_height_m > GATE_WAVE_M    (2.5 m) — only when marine data is present

2. wind_score (0–100):
     Gaussian centred on IDEAL_WIND_MID; σ = IDEAL_WIND_SIGMA.

3. sea_score (0–100):
     - Base: linear from 100 at 0 m waves → 0 at GATE_WAVE_M (2.5 m).
     - Chop penalty: subtract CHOP_PENALTY when wave_period_s < CHOP_PERIOD_S (4 s).
     - Score clamped 0–100.
     - When wave data unavailable: sea_score = 50 (neutral).

4. visibility_score (0–100):
     Linear: 100 at GOOD_VIS_M (10 000 m) → 0 at GATE_VIS_M (1 000 m).

5. wat_penalty (0–WAT_MAX_PENALTY = 25):
     Activated when:
       - current_speed_kt > WAT_MIN_CURRENT_KT (1.0 kt)
       - wind direction and current direction are opposed (using directions_opposed())
       - flood_dir_deg is known for the zone
     Magnitude proportional to current speed (capped at WAT_FULL_CURRENT_KT = 3.0 kt).

6. Final sailability:
     When marine data available:
       raw = WEIGHT_WIND_SEA × wind_score + WEIGHT_SEA × sea_score + WEIGHT_VIS_SEA × vis_score
     When marine data absent (v1 fallback):
       raw = WEIGHT_WIND × wind_score + WEIGHT_VIS × vis_score
     sailability = clip(raw − wat_penalty, 0, 100)
     If any gate fails: sailability = min(sailability, GATE_SCORE_CAP = 25)

Columns added:
    gates_passed       bool
    wind_score         float 0–100
    sea_score          float 0–100   (50 when no marine data)
    visibility_score   float 0–100
    wat_penalty        float 0–25    (0 when no tide / WAT data)
    sailability        float 0–100
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.domain.units import directions_opposed

# ---------------------------------------------------------------------------
# Profile constants (Phase 1/2 baseline cruiser; Phase 3 parameterises)
# ---------------------------------------------------------------------------

IDEAL_WIND_KT: tuple[float, float] = (10.0, 18.0)
IDEAL_WIND_MID: float = (IDEAL_WIND_KT[0] + IDEAL_WIND_KT[1]) / 2.0
IDEAL_WIND_SIGMA: float = 8.0

GATE_GUST_KT: float = 30.0
GATE_VIS_M: float = 1_000.0
GOOD_VIS_M: float = 10_000.0
GATE_WAVE_M: float = 2.5

CHOP_PERIOD_S: float = 4.0
CHOP_PENALTY: float = 25.0

WAT_MIN_CURRENT_KT: float = 1.0
WAT_FULL_CURRENT_KT: float = 3.0
WAT_MAX_PENALTY: float = 25.0

# v1 weights (no marine data)
WEIGHT_WIND: float = 0.55
WEIGHT_VIS: float = 0.45

# v2 weights (marine data available)
WEIGHT_WIND_SEA: float = 0.40
WEIGHT_SEA: float = 0.35
WEIGHT_VIS_SEA: float = 0.25

GATE_SCORE_CAP: float = 25.0


# ---------------------------------------------------------------------------
# Component scorers (vectorised)
# ---------------------------------------------------------------------------

def _wind_score(wind_kt: np.ndarray) -> np.ndarray:
    raw = 100.0 * np.exp(-0.5 * ((wind_kt - IDEAL_WIND_MID) / IDEAL_WIND_SIGMA) ** 2)
    return np.clip(raw, 0.0, 100.0)


def _visibility_score(vis_m: np.ndarray) -> np.ndarray:
    raw = (vis_m - GATE_VIS_M) / (GOOD_VIS_M - GATE_VIS_M) * 100.0
    return np.clip(raw, 0.0, 100.0)


def _sea_score(wave_height_m: np.ndarray, wave_period_s: np.ndarray) -> np.ndarray:
    base = np.clip((1.0 - wave_height_m / GATE_WAVE_M) * 100.0, 0.0, 100.0)
    chop = np.where(wave_period_s < CHOP_PERIOD_S, CHOP_PENALTY, 0.0)
    return np.clip(base - chop, 0.0, 100.0)


def _wat_penalty_vector(
    wind_dir_deg: np.ndarray,
    current_speed_kt: np.ndarray,
    flood_dir_deg: float,
    tide_rate_m_per_h: np.ndarray,
) -> np.ndarray:
    """Compute per-hour wind-against-tide penalty.

    Current direction is determined by the tide phase:
    - Rising tide (positive rate) → flood direction
    - Falling tide (negative rate) → ebb direction (flood + 180°)
    """
    n = len(wind_dir_deg)
    penalty = np.zeros(n, dtype=float)

    ebb_dir = (flood_dir_deg + 180.0) % 360.0

    for i in range(n):
        speed = float(current_speed_kt[i])
        if speed < WAT_MIN_CURRENT_KT:
            continue
        cur_dir = flood_dir_deg if float(tide_rate_m_per_h[i]) >= 0 else ebb_dir
        if directions_opposed(float(wind_dir_deg[i]), cur_dir):
            fraction = min(speed / WAT_FULL_CURRENT_KT, 1.0)
            penalty[i] = fraction * WAT_MAX_PENALTY

    return penalty


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def add_sailability_to_hourly(
    df: pd.DataFrame,
    flood_dir_deg: float | None = None,
) -> pd.DataFrame:
    """Add sailability score columns to an hourly DataFrame.

    Required columns: wind_kt, gust_kt, visibility_m
    Optional columns: wave_height_m, wave_period_s (activates sea_score + wave gate)
                      current_speed_kt, tide_rate_m_per_h (activates WAT penalty,
                      requires flood_dir_deg argument to be provided)

    Added columns: wind_score, sea_score, visibility_score, gates_passed,
                   wat_penalty, sailability
    """
    if df.empty:
        out = df.copy()
        for col in ("wind_score", "sea_score", "visibility_score",
                    "gates_passed", "wat_penalty", "sailability"):
            out[col] = pd.Series(dtype=float if col != "gates_passed" else bool)
        return out

    out = df.copy()

    wind_kt = out["wind_kt"].fillna(0.0).to_numpy(dtype=float)
    gust_kt = out["gust_kt"].fillna(0.0).to_numpy(dtype=float)
    vis_m = out["visibility_m"].fillna(GOOD_VIS_M).to_numpy(dtype=float)

    ws = _wind_score(wind_kt)
    vs = _visibility_score(vis_m)

    # --- Sea score ---
    has_marine = "wave_height_m" in out.columns and "wave_period_s" in out.columns
    if has_marine:
        wave_h = out["wave_height_m"].fillna(0.0).to_numpy(dtype=float)
        wave_p = out["wave_period_s"].fillna(8.0).to_numpy(dtype=float)
        ss = _sea_score(wave_h, wave_p)
    else:
        ss = np.full(len(out), 50.0)  # neutral when no data
        wave_h = np.zeros(len(out))   # used for gate check (no effect when no marine data)

    # --- Gates ---
    gust_gate = gust_kt <= GATE_GUST_KT
    vis_gate = vis_m >= GATE_VIS_M
    wave_gate = (wave_h <= GATE_WAVE_M) if has_marine else np.ones(len(out), dtype=bool)
    gates = gust_gate & vis_gate & wave_gate

    # --- WAT penalty ---
    has_tides = (
        flood_dir_deg is not None
        and "current_speed_kt" in out.columns
        and "tide_rate_m_per_h" in out.columns
    )
    if has_tides:
        cur_speed = out["current_speed_kt"].fillna(0.0).to_numpy(dtype=float)
        tide_rate = out["tide_rate_m_per_h"].fillna(0.0).to_numpy(dtype=float)
        wind_dir = out["wind_dir_deg"].fillna(0.0).to_numpy(dtype=float)
        wat = _wat_penalty_vector(wind_dir, cur_speed, flood_dir_deg, tide_rate)
    else:
        wat = np.zeros(len(out))

    # --- Final score ---
    if has_marine:
        raw = WEIGHT_WIND_SEA * ws + WEIGHT_SEA * ss + WEIGHT_VIS_SEA * vs
    else:
        raw = WEIGHT_WIND * ws + WEIGHT_VIS * vs

    sailability = np.where(gates, raw - wat, np.minimum(raw - wat, GATE_SCORE_CAP))
    sailability = np.clip(sailability, 0.0, 100.0)

    out["wind_score"] = ws
    out["sea_score"] = ss
    out["visibility_score"] = vs
    out["gates_passed"] = gates
    out["wat_penalty"] = wat
    out["sailability"] = sailability
    return out


# ---------------------------------------------------------------------------
# Aggregation helpers (unchanged from v1)
# ---------------------------------------------------------------------------

def best_windows(
    df_hourly: pd.DataFrame,
    window_hours: int = 3,
    top_n: int = 3,
) -> list[tuple[pd.Timestamp, pd.Timestamp, float]]:
    """Return top N consecutive windows ranked by average sailability."""
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
