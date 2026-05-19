"""Sailability score (v3) — vectorized, profile-driven, fully explainable.

v3 replaces all hardcoded thresholds with values from a SailorProfile.
When no profile is supplied the cruiser profile is used as the default,
making the function fully backward-compatible with v1 and v2 callers.

Formula (unchanged from v2; only thresholds are profile-driven)
-------
1. Hard safety gates (any failure → score capped at ≤ 25, gates_passed = False):
     - gust_kt       > profile.max_gust_kt
     - visibility_m  < profile.min_visibility_m
     - wave_height_m > profile.max_wave_m   (only when marine data present)

2. wind_score (0–100):
     Gaussian centred on profile.ideal_wind_mid; σ = IDEAL_WIND_SIGMA (fixed at 8).

3. sea_score (0–100):
     Base: linear 100 at 0 m → 0 at profile.max_wave_m.
     Chop penalty: deduct profile.chop_penalty when wave_period_s < profile.chop_period_s.
     Neutral (50) when no marine data.

4. visibility_score (0–100):
     Linear: 100 at GOOD_VIS_M → 0 at profile.min_visibility_m.

5. wat_penalty (0–WAT_MAX_PENALTY):
     Active when current_speed_kt > profile.wat_min_current_kt AND wind opposes current.

6. Final sailability:
     With marine data:  0.40 × wind + 0.35 × sea + 0.25 × vis  − wat_penalty
     Without:           0.55 × wind + 0.45 × vis  − wat_penalty
     Capped at 25 if any gate fails.

Columns added:
    gates_passed, wind_score, sea_score, visibility_score, wat_penalty, sailability
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.domain.units import directions_opposed

# ---------------------------------------------------------------------------
# Fixed constants (not profile-driven)
# ---------------------------------------------------------------------------

IDEAL_WIND_SIGMA: float = 8.0        # Gaussian std-dev — same for all profiles
GOOD_VIS_M: float = 10_000.0         # visibility at which vis_score = 100

WAT_FULL_CURRENT_KT: float = 3.0     # current speed at which WAT penalty is at max
WAT_MAX_PENALTY: float = 25.0        # max points deducted by wind-against-tide

# v1/v2 fallback weights
WEIGHT_WIND: float = 0.55
WEIGHT_VIS: float = 0.45

# v2/v3 weights with sea data
WEIGHT_WIND_SEA: float = 0.40
WEIGHT_SEA: float = 0.35
WEIGHT_VIS_SEA: float = 0.25

GATE_SCORE_CAP: float = 25.0

# Expose Phase 1/2 cruiser constants so imports in tests / UI don't break
IDEAL_WIND_KT: tuple[float, float] = (10.0, 18.0)
IDEAL_WIND_MID: float = 14.0
GATE_GUST_KT: float = 30.0
GATE_VIS_M: float = 1_000.0
GATE_WAVE_M: float = 2.5
CHOP_PERIOD_S: float = 4.0
CHOP_PENALTY: float = 25.0
WAT_MIN_CURRENT_KT: float = 1.0


# ---------------------------------------------------------------------------
# Component scorers (vectorised)
# ---------------------------------------------------------------------------

def _wind_score(wind_kt: np.ndarray, ideal_mid: float) -> np.ndarray:
    raw = 100.0 * np.exp(-0.5 * ((wind_kt - ideal_mid) / IDEAL_WIND_SIGMA) ** 2)
    return np.clip(raw, 0.0, 100.0)


def _visibility_score(vis_m: np.ndarray, gate_vis_m: float) -> np.ndarray:
    raw = (vis_m - gate_vis_m) / (GOOD_VIS_M - gate_vis_m) * 100.0
    return np.clip(raw, 0.0, 100.0)


def _sea_score(
    wave_height_m: np.ndarray,
    wave_period_s: np.ndarray,
    max_wave_m: float,
    chop_penalty: float,
    chop_period_s: float,
) -> np.ndarray:
    base = np.clip((1.0 - wave_height_m / max_wave_m) * 100.0, 0.0, 100.0)
    chop = np.where(wave_period_s < chop_period_s, chop_penalty, 0.0)
    return np.clip(base - chop, 0.0, 100.0)


def _wat_penalty_vector(
    wind_dir_deg: np.ndarray,
    current_speed_kt: np.ndarray,
    flood_dir_deg: float,
    tide_rate_m_per_h: np.ndarray,
    wat_min_current_kt: float,
) -> np.ndarray:
    n = len(wind_dir_deg)
    penalty = np.zeros(n, dtype=float)
    ebb_dir = (flood_dir_deg + 180.0) % 360.0
    for i in range(n):
        speed = float(current_speed_kt[i])
        if speed < wat_min_current_kt:
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
    profile: "SailorProfile | None" = None,  # noqa: F821 — imported lazily
) -> pd.DataFrame:
    """Add v3 sailability score columns to an hourly DataFrame.

    Required columns: wind_kt, gust_kt, visibility_m
    Optional columns: wave_height_m, wave_period_s, current_speed_kt,
                      tide_rate_m_per_h, wind_dir_deg
    profile: SailorProfile; defaults to cruiser when None.

    Added columns: wind_score, sea_score, visibility_score, gates_passed,
                   wat_penalty, sailability
    """
    if profile is None:
        from app.domain.profiles import get_default_profile
        profile = get_default_profile()

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

    ws = _wind_score(wind_kt, profile.ideal_wind_mid)
    vs = _visibility_score(vis_m, profile.min_visibility_m)

    # --- Sea score ---
    has_marine = "wave_height_m" in out.columns and "wave_period_s" in out.columns
    if has_marine:
        wave_h = out["wave_height_m"].fillna(0.0).to_numpy(dtype=float)
        wave_p = out["wave_period_s"].fillna(8.0).to_numpy(dtype=float)
        ss = _sea_score(wave_h, wave_p, profile.max_wave_m, profile.chop_penalty, profile.chop_period_s)
    else:
        ss = np.full(len(out), 50.0)
        wave_h = np.zeros(len(out))

    # --- Gates ---
    gust_gate = gust_kt <= profile.max_gust_kt
    vis_gate = vis_m >= profile.min_visibility_m
    wave_gate = (wave_h <= profile.max_wave_m) if has_marine else np.ones(len(out), dtype=bool)
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
        wat = _wat_penalty_vector(wind_dir, cur_speed, flood_dir_deg, tide_rate, profile.wat_min_current_kt)
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
# Aggregation helpers (unchanged)
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
    """Return Go/Maybe/No-Go from average sailability."""
    if sailability >= 65:
        return "GO"
    if sailability >= 35:
        return "MAYBE"
    return "NO-GO"
