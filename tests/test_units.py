"""Tests for domain/units.py."""
import math
import pytest
from app.domain.units import (
    ms_to_knots,
    kmh_to_knots,
    knots_to_kmh,
    m_to_ft,
    c_to_f,
    deg_to_compass,
    signed_deg_diff,
    directions_opposed,
)


class TestSpeedConversions:
    def test_ms_to_knots(self):
        assert ms_to_knots(0.0) == pytest.approx(0.0)
        assert ms_to_knots(1.0) == pytest.approx(1.94384, rel=1e-4)
        assert ms_to_knots(10.0) == pytest.approx(19.4384, rel=1e-4)

    def test_kmh_to_knots(self):
        assert kmh_to_knots(1.852) == pytest.approx(1.0, rel=1e-4)

    def test_knots_to_kmh(self):
        assert knots_to_kmh(1.0) == pytest.approx(1.852, rel=1e-4)

    def test_roundtrip(self):
        assert knots_to_kmh(kmh_to_knots(20.0)) == pytest.approx(20.0, rel=1e-4)


class TestDistanceConversions:
    def test_m_to_ft(self):
        assert m_to_ft(1.0) == pytest.approx(3.28084, rel=1e-4)
        assert m_to_ft(0.0) == 0.0


class TestTemperature:
    def test_freezing(self):
        assert c_to_f(0.0) == pytest.approx(32.0)

    def test_boiling(self):
        assert c_to_f(100.0) == pytest.approx(212.0)


class TestCompass:
    @pytest.mark.parametrize("deg,expected", [
        (0.0,   "N"),
        (45.0,  "NE"),
        (90.0,  "E"),
        (135.0, "SE"),
        (180.0, "S"),
        (225.0, "SW"),
        (270.0, "W"),
        (315.0, "NW"),
        (360.0, "N"),
        (11.0,  "N"),
        (12.0,  "NNE"),
    ])
    def test_deg_to_compass(self, deg, expected):
        assert deg_to_compass(deg) == expected


class TestAngularDiff:
    def test_same_direction(self):
        assert signed_deg_diff(0.0, 0.0) == pytest.approx(0.0)

    def test_positive_diff(self):
        assert signed_deg_diff(90.0, 0.0) == pytest.approx(90.0)

    def test_negative_diff(self):
        assert signed_deg_diff(0.0, 90.0) == pytest.approx(-90.0)

    def test_wrap_around(self):
        diff = signed_deg_diff(10.0, 350.0)
        assert diff == pytest.approx(20.0)

    def test_opposite(self):
        diff = signed_deg_diff(180.0, 0.0)
        assert abs(diff) == pytest.approx(180.0)


class TestDirectionsOpposed:
    def test_directly_opposed(self):
        # Wind from 270 (W), current flowing East (90 deg) → opposed
        assert directions_opposed(wind_deg=270.0, current_deg=90.0) is True

    def test_same_direction_not_opposed(self):
        # Wind from West (270), current flowing West (270) → same direction, not opposed
        assert directions_opposed(wind_deg=270.0, current_deg=270.0) is False

    def test_perpendicular_not_opposed(self):
        # Wind from North (0), current flowing East (90) → 90 deg off
        assert directions_opposed(wind_deg=0.0, current_deg=90.0) is False
