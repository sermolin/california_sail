"""Tests for app/domain/profiles.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.profiles import (
    SailorProfile,
    get_all_profiles,
    get_default_profile,
    get_profile_by_id,
    load_profiles,
)

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data"


class TestLoadProfiles:
    def test_loads_three_built_in_profiles(self):
        profiles = load_profiles()
        assert len(profiles) == 3

    def test_profile_ids(self):
        ids = {p.id for p in load_profiles()}
        assert ids == {"school", "cruiser", "racer"}

    def test_each_profile_has_required_fields(self):
        for p in load_profiles():
            assert p.name
            assert p.emoji
            assert len(p.ideal_wind_kt) == 2
            assert p.ideal_wind_kt[0] < p.ideal_wind_kt[1]
            assert p.max_gust_kt > 0
            assert p.max_wave_m > 0
            assert p.min_visibility_km > 0


class TestSailorProfile:
    def test_min_visibility_m_property(self):
        p = get_profile_by_id("cruiser")
        assert p.min_visibility_m == p.min_visibility_km * 1000.0

    def test_ideal_wind_mid_property(self):
        p = get_profile_by_id("cruiser")
        assert p.ideal_wind_mid == pytest.approx((p.ideal_wind_kt[0] + p.ideal_wind_kt[1]) / 2.0)

    def test_invalid_id_raises(self):
        with pytest.raises(ValueError):
            SailorProfile(
                id="", name="X", emoji="?", boat_size_hint="",
                ideal_wind_kt=(10.0, 18.0), max_gust_kt=30.0,
                max_wave_m=2.5, min_visibility_km=1.0,
                requires_low_chop=False, chop_penalty=25.0,
                chop_period_s=4.0, wat_min_current_kt=1.0,
            )

    def test_invalid_wind_range_raises(self):
        with pytest.raises(ValueError):
            SailorProfile(
                id="bad", name="Bad", emoji="?", boat_size_hint="",
                ideal_wind_kt=(18.0, 10.0),   # reversed
                max_gust_kt=30.0, max_wave_m=2.5, min_visibility_km=1.0,
                requires_low_chop=False, chop_penalty=25.0,
                chop_period_s=4.0, wat_min_current_kt=1.0,
            )


class TestGetProfileById:
    def test_returns_correct_profile(self):
        p = get_profile_by_id("school")
        assert p.id == "school"

    def test_unknown_id_falls_back_to_cruiser(self):
        p = get_profile_by_id("nonexistent")
        assert p.id == "cruiser"

    def test_default_profile_is_cruiser(self):
        assert get_default_profile().id == "cruiser"


class TestProfileThresholdOrdering:
    """Racer should tolerate more wind/waves, school less."""

    def test_racer_higher_gust_gate_than_school(self):
        school = get_profile_by_id("school")
        racer = get_profile_by_id("racer")
        assert racer.max_gust_kt > school.max_gust_kt

    def test_racer_higher_wave_gate_than_school(self):
        school = get_profile_by_id("school")
        racer = get_profile_by_id("racer")
        assert racer.max_wave_m > school.max_wave_m

    def test_racer_higher_ideal_wind_than_school(self):
        school = get_profile_by_id("school")
        racer = get_profile_by_id("racer")
        assert racer.ideal_wind_mid > school.ideal_wind_mid

    def test_school_higher_chop_penalty_than_racer(self):
        school = get_profile_by_id("school")
        racer = get_profile_by_id("racer")
        assert school.chop_penalty > racer.chop_penalty
