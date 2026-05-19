"""Sailor profile domain model — drives scoring thresholds (Phase 3).

A SailorProfile bundles all scoring thresholds for a particular type of sailor.
Profiles are loaded from data/sailor_profiles.yaml.  Three built-in presets ship
with the app: school, cruiser (the Phase 1/2 baseline), and racer.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_YAML = Path(__file__).resolve().parent.parent.parent / "data" / "sailor_profiles.yaml"


@dataclass(frozen=True)
class SailorProfile:
    """Scoring thresholds for a specific type of sailor / boat."""

    id: str
    name: str
    emoji: str
    boat_size_hint: str
    ideal_wind_kt: tuple[float, float]   # (low, high) sweet-spot range
    max_gust_kt: float                   # hard No-Go gate
    max_wave_m: float                    # hard No-Go gate (requires marine data)
    min_visibility_km: float             # hard No-Go gate
    requires_low_chop: bool
    chop_penalty: float                  # score deduction when choppy
    chop_period_s: float                 # wave period threshold for chop detection
    wat_min_current_kt: float            # current speed below which WAT penalty inactive

    @property
    def min_visibility_m(self) -> float:
        return self.min_visibility_km * 1_000.0

    @property
    def ideal_wind_mid(self) -> float:
        return (self.ideal_wind_kt[0] + self.ideal_wind_kt[1]) / 2.0

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("SailorProfile id must be non-empty")
        if len(self.ideal_wind_kt) != 2 or self.ideal_wind_kt[0] >= self.ideal_wind_kt[1]:
            raise ValueError(f"ideal_wind_kt must be (low, high) with low < high, got {self.ideal_wind_kt}")
        if self.max_gust_kt <= 0:
            raise ValueError("max_gust_kt must be positive")


def _parse_profile(raw: dict) -> SailorProfile:
    w = raw.get("ideal_wind_kt", [10.0, 18.0])
    return SailorProfile(
        id=str(raw["id"]),
        name=str(raw.get("name", raw["id"])),
        emoji=str(raw.get("emoji", "⛵")),
        boat_size_hint=str(raw.get("boat_size_hint", "")),
        ideal_wind_kt=(float(w[0]), float(w[1])),
        max_gust_kt=float(raw.get("max_gust_kt", 30.0)),
        max_wave_m=float(raw.get("max_wave_m", 2.5)),
        min_visibility_km=float(raw.get("min_visibility_km", 1.0)),
        requires_low_chop=bool(raw.get("requires_low_chop", False)),
        chop_penalty=float(raw.get("chop_penalty", 25.0)),
        chop_period_s=float(raw.get("chop_period_s", 4.0)),
        wat_min_current_kt=float(raw.get("wat_min_current_kt", 1.0)),
    )


def load_profiles(path: str | Path = _DEFAULT_YAML) -> list[SailorProfile]:
    """Load all profiles from a YAML file."""
    with open(path, encoding="utf-8") as fh:
        data: Any = yaml.safe_load(fh)
    if not isinstance(data, list):
        raise ValueError(f"sailor_profiles.yaml must contain a YAML list, got {type(data)}")
    return [_parse_profile(p) for p in data]


def get_profile_by_id(
    profile_id: str,
    profiles: list[SailorProfile] | None = None,
) -> SailorProfile:
    """Return a profile by id; falls back to the cruiser profile if not found."""
    if profiles is None:
        profiles = load_profiles()
    match = next((p for p in profiles if p.id == profile_id), None)
    if match is None:
        match = next((p for p in profiles if p.id == "cruiser"), profiles[0])
    return match


# ---------------------------------------------------------------------------
# Module-level singletons — loaded once, reused everywhere
# ---------------------------------------------------------------------------

_PROFILES_CACHE: list[SailorProfile] | None = None


def get_all_profiles() -> list[SailorProfile]:
    """Return all profiles, loading from YAML once per process."""
    global _PROFILES_CACHE
    if _PROFILES_CACHE is None:
        _PROFILES_CACHE = load_profiles()
    return _PROFILES_CACHE


def get_default_profile() -> SailorProfile:
    """Return the cruiser profile (Phase 1/2 default)."""
    return get_profile_by_id("cruiser")
