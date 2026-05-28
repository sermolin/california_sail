"""Pure filter helpers for zone forecast results — no Streamlit dependency."""
from __future__ import annotations

from app.services.forecast_service import ZoneForecast


def filter_forecasts(results: list[ZoneForecast], query: str) -> list[ZoneForecast]:
    """Return results whose zone name or id contains query (case-insensitive).

    An empty or whitespace-only query returns the full list unchanged.
    """
    q = query.strip().lower()
    if not q:
        return results
    return [
        r for r in results
        if q in r.zone.name.lower() or q in r.zone.id.lower()
    ]


def apply_top_n(results: list[ZoneForecast], n: int | None) -> list[ZoneForecast]:
    """Return at most the first n items (already sorted best-first).

    n=None or n <= 0 returns all results unchanged.
    """
    if n is None or n <= 0:
        return results
    return results[:n]


def default_zone_index(results: list[ZoneForecast], favorite_zone_id: str | None) -> int:
    """Return the index of the favorite zone in results, or 0 if not found."""
    if not favorite_zone_id or not results:
        return 0
    for i, r in enumerate(results):
        if r.zone.id == favorite_zone_id:
            return i
    return 0
