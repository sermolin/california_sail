"""Sailing region and zone models with YAML loader."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SailingZone:
    """A specific sailing area within a region."""

    id: str
    name: str
    latitude: float
    longitude: float
    exposure: str              # "sheltered" | "open" | "channel"
    hazards: list[str]         # human-readable hazard labels
    flood_dir_deg: float | None = None  # direction current flows TO during flood tide (Phase 2)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("SailingZone id must be non-empty")
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"latitude must be between -90 and 90, got {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"longitude must be between -180 and 180, got {self.longitude}")
        if self.exposure not in ("sheltered", "open", "channel"):
            raise ValueError(f"exposure must be 'sheltered', 'open', or 'channel', got {self.exposure!r}")


@dataclass(frozen=True)
class SailingRegion:
    """A sailing region containing one or more sailing zones."""

    id: str
    name: str
    country: str
    timezone: str              # e.g. "America/Los_Angeles", "Europe/Rome"
    tide_station_id: str | None  # NOAA CO-OPS station id (US only)
    nws_zone: str | None         # NOAA NWS marine zone id (US only)
    zones: list[SailingZone]

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("SailingRegion id must be non-empty")
        if not self.zones:
            raise ValueError(f"Region {self.id!r} must have at least one zone")

    @property
    def default_zone(self) -> SailingZone:
        """Return the first zone as the default for this region."""
        return self.zones[0]

    def has_noaa_tides(self) -> bool:
        return self.tide_station_id is not None

    def has_noaa_warnings(self) -> bool:
        return self.nws_zone is not None


def load_regions(path: str | Path) -> list[SailingRegion]:
    """Load sailing regions from a YAML file. Validates unique IDs and required fields."""
    path = Path(path)
    if not path.exists():
        return []

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not data:
        return []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "regions" in data:
        items = data["regions"]
    else:
        items = []

    if not isinstance(items, list):
        raise ValueError("sailing_areas.yaml must contain a list of region objects")

    seen_region_ids: set[str] = set()
    regions: list[SailingRegion] = []

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"region at index {i} must be an object")

        rid = _require_str(item, "id", f"region[{i}]")
        if rid in seen_region_ids:
            raise ValueError(f"duplicate region id: {rid!r}")
        seen_region_ids.add(rid)

        zones = _load_zones(item.get("zones") or [], rid)

        regions.append(
            SailingRegion(
                id=rid,
                name=_require_str(item, "name", f"region[{i}]"),
                country=_get_str(item, "country", default=""),
                timezone=_get_str(item, "timezone", default="UTC"),
                tide_station_id=_get_optional_str(item, "tide_station_id"),
                nws_zone=_get_optional_str(item, "nws_zone"),
                zones=zones,
            )
        )

    return regions


def _load_zones(raw_zones: list, region_id: str) -> list[SailingZone]:
    if not raw_zones:
        raise ValueError(f"region {region_id!r} has no zones")

    seen_zone_ids: set[str] = set()
    zones: list[SailingZone] = []

    for j, z in enumerate(raw_zones):
        if not isinstance(z, dict):
            raise ValueError(f"zone at region {region_id!r}[{j}] must be an object")
        zid = _require_str(z, "id", f"region {region_id!r} zone[{j}]")
        if zid in seen_zone_ids:
            raise ValueError(f"duplicate zone id {zid!r} in region {region_id!r}")
        seen_zone_ids.add(zid)

        hazards_raw = z.get("hazards") or []
        hazards = [str(h) for h in hazards_raw] if isinstance(hazards_raw, list) else []

        zones.append(
            SailingZone(
                id=zid,
                name=_require_str(z, "name", f"zone {zid!r}"),
                latitude=_require_float(z, "latitude", f"zone {zid!r}"),
                longitude=_require_float(z, "longitude", f"zone {zid!r}"),
                exposure=_get_str(z, "exposure", default="open"),
                hazards=hazards,
                flood_dir_deg=_get_optional_float(z, "flood_dir_deg"),
            )
        )

    return zones


def _require_str(obj: dict, key: str, ctx: str) -> str:
    if key not in obj:
        raise ValueError(f"missing required field {key!r} in {ctx}")
    v = obj[key]
    s = str(v).strip() if v is not None else ""
    if not s:
        raise ValueError(f"required field {key!r} must be non-empty in {ctx}")
    return s


def _get_str(obj: dict, key: str, default: str = "") -> str:
    v = obj.get(key, default)
    if v is None:
        return default
    return str(v).strip() or default


def _get_optional_str(obj: dict, key: str) -> str | None:
    v = obj.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _get_optional_float(obj: dict, key: str) -> float | None:
    v = obj.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _require_float(obj: dict, key: str, ctx: str) -> float:
    if key not in obj:
        raise ValueError(f"missing required field {key!r} in {ctx}")
    try:
        return float(obj[key])
    except (TypeError, ValueError) as e:
        raise ValueError(f"invalid {key!r} in {ctx}: must be a number") from e
