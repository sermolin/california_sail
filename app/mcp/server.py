"""California Sail MCP server.

Exposes 8 sailing-forecast tools via the Model Context Protocol (MCP).

Transport modes
---------------
stdio (default)
    For local MCP clients: Cursor, Claude Desktop.  The client spawns this
    process and communicates over stdin/stdout.

sse
    HTTP + Server-Sent Events.  For remote agents, future Telegram/Slack bots.
    Start with ``--transport sse [--host 127.0.0.1] [--port 8765]`` and point
    agents at ``http://host:port/sse``.

Usage
-----
.. code-block:: bash

    # stdio (default) — used by Cursor / Claude Desktop configs
    python -m app.mcp.server

    # HTTP/SSE — used by remote agents
    python -m app.mcp.server --transport sse --port 8765

    # Help
    python -m app.mcp.server --help
"""
from __future__ import annotations

import argparse
import logging
import sys

from mcp.server.fastmcp import FastMCP

import app.mcp.tools as _tools

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)

_log = logging.getLogger(__name__)


def _build_server(host: str = "127.0.0.1", port: int = 8765) -> FastMCP:
    """Construct and return the FastMCP server with all 8 tools registered."""
    server = FastMCP(
        name="california-sail",
        instructions=(
            "California Sail provides live sailing-conditions forecasts for "
            "San Francisco Bay, Puget Sound (Seattle), and Sardinia. "
            "Use list_regions → list_zones to discover valid IDs, then call "
            "get_zone_forecast or compare_zones_in_region for conditions. "
            "Always check get_active_warnings for safety alerts."
        ),
        host=host,
        port=port,
    )

    @server.tool()
    def list_regions() -> list:
        """List all available sailing regions (id, name, country, n_zones)."""
        return _tools.list_regions()

    @server.tool()
    def list_zones(region_id: str) -> list:
        """List all sailing zones within a region.

        Args:
            region_id: Region identifier (e.g. "sf-bay", "puget-sound", "sardinia").
        """
        return _tools.list_zones(region_id)

    @server.tool()
    def list_profiles() -> list:
        """List all available sailor profiles with scoring thresholds."""
        return _tools.list_profiles()

    @server.tool()
    def get_zone_forecast(
        zone_id: str,
        profile_id: str = "cruiser",
        days: int = 3,
        summary: bool = True,
    ) -> dict:
        """Fetch and score the sailing forecast for a single zone.

        Args:
            zone_id: Zone identifier (e.g. "city-front", "shilshole", "stintino").
            profile_id: Sailor profile — "school", "cruiser" (default), or "racer".
            days: Forecast horizon in days (1-7, default 3).
            summary: True (default) = compact response without per-hour rows.
                     False = include up to 72 hours of hourly detail.
        """
        return _tools.get_zone_forecast(
            zone_id=zone_id, profile_id=profile_id, days=days, summary=summary,
        )

    @server.tool()
    def compare_zones_in_region(
        region_id: str,
        profile_id: str = "cruiser",
    ) -> list:
        """Compare all zones in a region and rank by current sailability.

        Args:
            region_id: Region identifier (e.g. "sf-bay").
            profile_id: Sailor profile for scoring (default "cruiser").
        """
        return _tools.compare_zones_in_region(region_id=region_id, profile_id=profile_id)

    @server.tool()
    def best_sail_windows(
        zone_id: str,
        profile_id: str = "cruiser",
        days: int = 3,
        top_n: int = 3,
    ) -> list:
        """Find the top sailing windows (best sustained sailability blocks) in a zone.

        Args:
            zone_id: Zone identifier.
            profile_id: Sailor profile (default "cruiser").
            days: Forecast horizon in days (1-7, default 3).
            top_n: Maximum windows to return (default 3).
        """
        return _tools.best_sail_windows(
            zone_id=zone_id, profile_id=profile_id, days=days, top_n=top_n,
        )

    @server.tool()
    def get_active_warnings(region_id: str) -> list:
        """Return any active NOAA marine warnings for a US region.

        Returns an empty list for non-US regions or when no warnings are active.

        Args:
            region_id: Region identifier (e.g. "sf-bay", "puget-sound").
        """
        return _tools.get_active_warnings(region_id)

    @server.tool()
    def explain_score(
        zone_id: str,
        hour_offset: int = 0,
        profile_id: str = "cruiser",
    ) -> dict:
        """Explain the sailability score for a specific hour in a zone forecast.

        Returns component scores, gate status, wind-against-tide penalty, and
        a plain-language summary string.

        Args:
            zone_id: Zone identifier.
            hour_offset: Hour index into forecast (0 = now, 1 = next hour, …).
            profile_id: Sailor profile (default "cruiser").
        """
        return _tools.explain_score(
            zone_id=zone_id, hour_offset=hour_offset, profile_id=profile_id,
        )

    return server


# Module-level server instance (stdio defaults; SSE overrides at __main__ time)
mcp = _build_server()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.mcp.server",
        description="California Sail MCP server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport: 'stdio' for Cursor/Claude Desktop, 'sse' for HTTP (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for SSE transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind for SSE transport (default: 8765)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()

    if args.transport == "stdio":
        _log.info("Starting California Sail MCP server (stdio)")
        mcp.run(transport="stdio")
    else:
        _log.info(
            "Starting California Sail MCP server (SSE) on %s:%s",
            args.host, args.port,
        )
        sse_server = _build_server(host=args.host, port=args.port)
        sse_server.run(transport="sse")
