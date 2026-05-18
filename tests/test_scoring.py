"""Tests for domain/scoring.py v1 + v2."""
import numpy as np
import pandas as pd
import pytest

from app.domain.scoring import (
    GATE_GUST_KT,
    GATE_VIS_M,
    GATE_WAVE_M,
    GOOD_VIS_M,
    IDEAL_WIND_KT,
    IDEAL_WIND_MID,
    WAT_MAX_PENALTY,
    add_sailability_to_hourly,
    best_windows,
    daily_sailability_avg,
    verdict,
)


def _make_df(wind_kt=15.0, gust_kt=20.0, vis_m=15000.0, n=6) -> pd.DataFrame:
    """Helper: build a minimal hourly DataFrame (v1, no marine/tide data)."""
    ts = pd.date_range("2026-05-15", periods=n, freq="h")
    return pd.DataFrame({
        "timestamp": ts,
        "wind_kt": [wind_kt] * n,
        "gust_kt": [gust_kt] * n,
        "wind_dir_deg": [270.0] * n,
        "visibility_m": [vis_m] * n,
    })


def _make_df_v2(wind_kt=15.0, gust_kt=20.0, vis_m=15000.0,
                wave_h=0.5, wave_p=8.0,
                current_kt=0.0, tide_rate=0.0,
                n=6) -> pd.DataFrame:
    """Helper: build a full v2 hourly DataFrame with marine + tide columns."""
    df = _make_df(wind_kt=wind_kt, gust_kt=gust_kt, vis_m=vis_m, n=n)
    df["wave_height_m"] = wave_h
    df["wave_period_s"] = wave_p
    df["current_speed_kt"] = current_kt
    df["tide_rate_m_per_h"] = tide_rate
    return df


class TestAddSailabilityV1:
    def test_columns_added(self):
        df = _make_df()
        out = add_sailability_to_hourly(df)
        for col in ("wind_score", "sea_score", "visibility_score",
                    "gates_passed", "wat_penalty", "sailability"):
            assert col in out.columns

    def test_ideal_wind_scores_near_100(self):
        df = _make_df(wind_kt=IDEAL_WIND_MID, gust_kt=10.0, vis_m=GOOD_VIS_M)
        out = add_sailability_to_hourly(df)
        assert float(out["wind_score"].mean()) > 95.0

    def test_gust_gate_caps_score(self):
        df = _make_df(wind_kt=15.0, gust_kt=GATE_GUST_KT + 5.0, vis_m=GOOD_VIS_M)
        out = add_sailability_to_hourly(df)
        assert not out["gates_passed"].any()
        assert float(out["sailability"].max()) <= 25.0 + 1e-6

    def test_visibility_gate_caps_score(self):
        df = _make_df(wind_kt=15.0, gust_kt=10.0, vis_m=GATE_VIS_M - 100.0)
        out = add_sailability_to_hourly(df)
        assert not out["gates_passed"].any()
        assert float(out["sailability"].max()) <= 25.0 + 1e-6

    def test_score_range(self):
        df = _make_df(wind_kt=IDEAL_WIND_MID, gust_kt=GATE_GUST_KT - 1, vis_m=GOOD_VIS_M)
        out = add_sailability_to_hourly(df)
        assert (out["sailability"] >= 0.0).all()
        assert (out["sailability"] <= 100.0).all()

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame(columns=["timestamp", "wind_kt", "gust_kt", "wind_dir_deg", "visibility_m"])
        out = add_sailability_to_hourly(df)
        assert out.empty

    def test_zero_wind_scores_lower_than_ideal(self):
        df_zero = _make_df(wind_kt=0.0, gust_kt=0.0, vis_m=GOOD_VIS_M)
        df_ideal = _make_df(wind_kt=IDEAL_WIND_MID, gust_kt=10.0, vis_m=GOOD_VIS_M)
        out_zero = add_sailability_to_hourly(df_zero)
        out_ideal = add_sailability_to_hourly(df_ideal)
        assert float(out_zero["sailability"].mean()) < float(out_ideal["sailability"].mean())

    def test_sea_score_neutral_when_no_marine(self):
        df = _make_df()
        out = add_sailability_to_hourly(df)
        assert (out["sea_score"] == 50.0).all()

    def test_wat_penalty_zero_when_no_tides(self):
        df = _make_df()
        out = add_sailability_to_hourly(df)
        assert (out["wat_penalty"] == 0.0).all()


class TestAddSailabilityV2SeaScore:
    def test_calm_seas_score_higher_than_rough(self):
        df_calm = _make_df_v2(wave_h=0.3, wave_p=10.0)
        df_rough = _make_df_v2(wave_h=2.0, wave_p=6.0)
        out_calm = add_sailability_to_hourly(df_calm)
        out_rough = add_sailability_to_hourly(df_rough)
        assert float(out_calm["sea_score"].mean()) > float(out_rough["sea_score"].mean())

    def test_wave_height_gate_caps_score(self):
        df = _make_df_v2(wave_h=GATE_WAVE_M + 0.5, wave_p=8.0)
        out = add_sailability_to_hourly(df)
        assert not out["gates_passed"].any()
        assert float(out["sailability"].max()) <= 25.0 + 1e-6

    def test_chop_penalty_with_short_period(self):
        df_chop = _make_df_v2(wave_h=0.5, wave_p=2.0)    # choppy
        df_swell = _make_df_v2(wave_h=0.5, wave_p=10.0)  # nice swell
        out_chop = add_sailability_to_hourly(df_chop)
        out_swell = add_sailability_to_hourly(df_swell)
        assert float(out_chop["sea_score"].mean()) < float(out_swell["sea_score"].mean())

    def test_sea_score_range(self):
        df = _make_df_v2(wave_h=1.0, wave_p=7.0)
        out = add_sailability_to_hourly(df)
        assert (out["sea_score"] >= 0.0).all()
        assert (out["sea_score"] <= 100.0).all()


class TestAddSailabilityV2WatPenalty:
    def test_no_penalty_below_min_current(self):
        # Calm current, even with direct wind opposition
        df = _make_df_v2(wind_kt=15.0, current_kt=0.5, tide_rate=0.5)
        df["wind_dir_deg"] = 55.0   # flood direction from north (typical SF)
        out = add_sailability_to_hourly(df, flood_dir_deg=55.0)
        assert (out["wat_penalty"] == 0.0).all()

    def test_penalty_active_when_opposed_and_strong_current(self):
        # Wind FROM 235 (opposite of flood direction 55)
        n = 6
        df = _make_df_v2(wind_kt=15.0, current_kt=3.0, tide_rate=0.3, n=n)
        df["wind_dir_deg"] = 235.0   # ~ ebb direction — opposed to flood current at 55°
        out = add_sailability_to_hourly(df, flood_dir_deg=55.0)
        assert (out["wat_penalty"] > 0).all()
        assert (out["wat_penalty"] <= WAT_MAX_PENALTY + 1e-6).all()

    def test_no_penalty_when_no_flood_dir_deg(self):
        df = _make_df_v2(current_kt=3.0, tide_rate=0.3)
        df["wind_dir_deg"] = 235.0
        out = add_sailability_to_hourly(df, flood_dir_deg=None)
        assert (out["wat_penalty"] == 0.0).all()

    def test_sailability_reduced_by_wat_penalty(self):
        n = 6
        df_no_wat = _make_df_v2(wind_kt=15.0, current_kt=0.0, tide_rate=0.0, n=n)
        df_wat = _make_df_v2(wind_kt=15.0, current_kt=3.0, tide_rate=0.3, n=n)
        df_wat["wind_dir_deg"] = 235.0
        df_no_wat["wind_dir_deg"] = 235.0
        out_no_wat = add_sailability_to_hourly(df_no_wat, flood_dir_deg=55.0)
        out_wat = add_sailability_to_hourly(df_wat, flood_dir_deg=55.0)
        assert float(out_wat["sailability"].mean()) < float(out_no_wat["sailability"].mean())


class TestBestWindows:
    def test_returns_top_n(self):
        df = _make_df(n=12)
        df = add_sailability_to_hourly(df)
        wins = best_windows(df, window_hours=3, top_n=3)
        assert len(wins) <= 3

    def test_windows_sorted_descending(self):
        df = _make_df(n=12)
        df = add_sailability_to_hourly(df)
        wins = best_windows(df, window_hours=3, top_n=5)
        scores = [w[2] for w in wins]
        assert scores == sorted(scores, reverse=True)

    def test_too_short_returns_empty(self):
        df = _make_df(n=2)
        df = add_sailability_to_hourly(df)
        assert best_windows(df, window_hours=3) == []

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame(columns=["timestamp", "sailability"])
        assert best_windows(df) == []

    def test_window_tuple_structure(self):
        df = _make_df(n=12)
        df = add_sailability_to_hourly(df)
        wins = best_windows(df, window_hours=3, top_n=1)
        start, end, score = wins[0]
        assert isinstance(start, pd.Timestamp)
        assert isinstance(end, pd.Timestamp)
        assert 0.0 <= score <= 100.0


class TestDailySailabilityAvg:
    def test_aggregates_by_date(self):
        df = _make_df(n=24)
        df = add_sailability_to_hourly(df)
        daily = daily_sailability_avg(df)
        assert "date" in daily.columns
        assert "sailability_avg" in daily.columns
        assert len(daily) >= 1

    def test_empty_returns_empty(self):
        df = pd.DataFrame(columns=["timestamp", "sailability"])
        result = daily_sailability_avg(df)
        assert result.empty


class TestVerdict:
    @pytest.mark.parametrize("score,expected", [
        (0.0,  "NO-GO"),
        (34.9, "NO-GO"),
        (35.0, "MAYBE"),
        (64.9, "MAYBE"),
        (65.0, "GO"),
        (100.0,"GO"),
    ])
    def test_verdict_boundaries(self, score, expected):
        assert verdict(score) == expected
