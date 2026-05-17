"""Tests for domain/scoring.py v1."""
import numpy as np
import pandas as pd
import pytest

from app.domain.scoring import (
    GATE_GUST_KT,
    GATE_VIS_M,
    GOOD_VIS_M,
    IDEAL_WIND_KT,
    IDEAL_WIND_MID,
    add_sailability_to_hourly,
    best_windows,
    daily_sailability_avg,
    verdict,
)


def _make_df(wind_kt=15.0, gust_kt=20.0, vis_m=15000.0, n=6) -> pd.DataFrame:
    """Helper: build a minimal hourly DataFrame."""
    ts = pd.date_range("2026-05-15", periods=n, freq="h")
    return pd.DataFrame({
        "timestamp": ts,
        "wind_kt": [wind_kt] * n,
        "gust_kt": [gust_kt] * n,
        "visibility_m": [vis_m] * n,
    })


class TestAddSailability:
    def test_columns_added(self):
        df = _make_df()
        out = add_sailability_to_hourly(df)
        for col in ("wind_score", "visibility_score", "gates_passed", "sailability"):
            assert col in out.columns

    def test_ideal_wind_scores_near_100(self):
        df = _make_df(wind_kt=IDEAL_WIND_MID, gust_kt=10.0, vis_m=GOOD_VIS_M)
        out = add_sailability_to_hourly(df)
        assert float(out["wind_score"].mean()) > 95.0

    def test_gust_gate_caps_score(self):
        df = _make_df(wind_kt=15.0, gust_kt=GATE_GUST_KT + 5.0, vis_m=GOOD_VIS_M)
        out = add_sailability_to_hourly(df)
        assert out["gates_passed"].all() is False or not out["gates_passed"].any()
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
        df = pd.DataFrame(columns=["timestamp", "wind_kt", "gust_kt", "visibility_m"])
        out = add_sailability_to_hourly(df)
        assert out.empty

    def test_zero_wind_scores_lower_than_ideal(self):
        df_zero = _make_df(wind_kt=0.0, gust_kt=0.0, vis_m=GOOD_VIS_M)
        df_ideal = _make_df(wind_kt=IDEAL_WIND_MID, gust_kt=10.0, vis_m=GOOD_VIS_M)
        out_zero = add_sailability_to_hourly(df_zero)
        out_ideal = add_sailability_to_hourly(df_ideal)
        assert float(out_zero["sailability"].mean()) < float(out_ideal["sailability"].mean())

    def test_very_high_wind_scores_lower_than_ideal(self):
        df_high = _make_df(wind_kt=50.0, gust_kt=25.0, vis_m=GOOD_VIS_M)
        df_ideal = _make_df(wind_kt=IDEAL_WIND_MID, gust_kt=10.0, vis_m=GOOD_VIS_M)
        out_high = add_sailability_to_hourly(df_high)
        out_ideal = add_sailability_to_hourly(df_ideal)
        assert float(out_high["sailability"].mean()) < float(out_ideal["sailability"].mean())


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
