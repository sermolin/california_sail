"""Region service: fetch all zones in a region and rank by sailability."""
from __future__ import annotations

import concurrent.futures
import logging
from pathlib import Path

from app.domain.profiles import SailorProfile, get_default_profile
from app.domain.regions import SailingRegion, SailingZone, load_regions
from app.services.forecast_service import ZoneForecast, get_zone_forecast

_log = logging.getLogger(__name__)


def get_all_zone_forecasts(
    region: SailingRegion,
    days: int = 7,
    profile: SailorProfile | None = None,
) -> list[ZoneForecast]:
    """Fetch forecasts for all zones in a region, sorted best-to-worst."""
    if profile is None:
        profile = get_default_profile()

    def _fetch_zone(zone: SailingZone) -> ZoneForecast | None:
        try:
            return get_zone_forecast(
                zone_id=zone.id,
                region_id=region.id,
                lat=zone.latitude,
                lon=zone.longitude,
                zone_name=zone.name,
                region_name=region.name,
                country=region.country,
                timezone=region.timezone,
                tide_station_id=region.tide_station_id,
                nws_zone=region.nws_zone,
                exposure=zone.exposure,
                hazards=tuple(zone.hazards),
                flood_dir_deg=zone.flood_dir_deg,
                days=days,
                forecast_timezone=region.timezone,
                profile_id=profile.id,
            )
        except Exception as exc:
            _log.warning("Could not fetch forecast for zone %s: %s", zone.id, exc)
            return None

    results: list[ZoneForecast] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_zone, z): z for z in region.zones}
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            if result is not None:
                results.append(result)

    results.sort(key=lambda r: -r.current_sailability)
    return results


def list_regions(sailing_areas_path: str | Path) -> list[SailingRegion]:
    """Load all regions from YAML."""
    return load_regions(sailing_areas_path)


def get_region_by_name(
    regions: list[SailingRegion],
    name: str,
) -> SailingRegion | None:
    """Return the first region matching the given name (case-insensitive)."""
    name_lower = name.strip().lower()
    return next((r for r in regions if r.name.lower() == name_lower), None)
