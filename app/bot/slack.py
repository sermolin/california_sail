"""California Sail Slack bot — event handlers, slash commands, and entry point.

Slash commands (register all at https://api.slack.com/apps, pointing to
POST /slack/events on the deployed service):
  /forecast <zone_id> [profile_id]   Forecast for a zone
  /compare  <region_id> [profile_id] Rank all zones in a region
  /windows  <zone_id> [profile_id]   Best sailing windows
  /warnings <region_id>              Active marine warnings
  /explain  <zone_id> [profile_id]   Score breakdown
  /regions                           List all regions
  /zones    <region_id>              List zones in a region
  /profiles                          List sailor profiles
  /reset                             Clear your conversation history

Natural language
----------------
Direct messages and @-mentions are routed to the AI agent (same OpenRouter
agent used by the Telegram bot). Requires OPENROUTER_API_KEY.

Configuration
-------------
SLACK_BOT_TOKEN      xoxb-… from OAuth & Permissions
SLACK_SIGNING_SECRET From Basic Information in the Slack app dashboard

Both are required; the bot is disabled and /slack/events returns 503
if either is absent.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re

import app.mcp.tools as _tools
from app.bot.agent import reset_history, run_agent
from app.bot.slack_formatters import (
    format_compare,
    format_explain,
    format_forecast,
    format_profiles,
    format_regions,
    format_warnings,
    format_windows,
    format_zones,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slack_uid(user_id: str) -> int:
    """Convert a Slack string user ID to a stable int for ConversationStore.

    Uses MD5 so the mapping is deterministic across Python processes
    (unlike the built-in hash() which is randomised by PYTHONHASHSEED).
    """
    return int(hashlib.md5(user_id.encode()).hexdigest()[:15], 16)


def _parse_args(text: str) -> list[str]:
    """Split slash-command argument string into a list of tokens."""
    return text.strip().split() if text and text.strip() else []


def _arg(parts: list[str], index: int, default: str = "") -> str:
    return parts[index] if index < len(parts) else default


def _strip_mention(text: str) -> str:
    """Remove leading <@USERID> mention from a channel message."""
    return re.sub(r"^<@[A-Z0-9]+>\s*", "", text or "").strip()


# ---------------------------------------------------------------------------
# Slack app (lazy-built so missing env vars don't crash on import)
# ---------------------------------------------------------------------------

_slack_app = None
_slack_handler = None


def build_slack_handler():
    """Build and return the AsyncSlackRequestHandler.

    Returns None if SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET are not set.
    """
    global _slack_app, _slack_handler

    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "").strip()

    if not token or not signing_secret:
        _log.warning(
            "SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET not set — Slack bot disabled."
        )
        return None

    from slack_bolt.async_app import AsyncApp
    from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

    _slack_app = AsyncApp(token=token, signing_secret=signing_secret)
    _register_handlers(_slack_app)
    _slack_handler = AsyncSlackRequestHandler(_slack_app)
    return _slack_handler


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------

def _register_handlers(app) -> None:  # app: AsyncApp
    """Attach all slash command and event handlers to the Slack app."""

    # ── Slash commands ──────────────────────────────────────────────────────

    @app.command("/regions")
    async def cmd_regions(ack, respond):
        await ack()
        try:
            result = _tools.list_regions()
            await respond(format_regions(result))
        except Exception as exc:
            _log.exception("slack /regions failed")
            await respond(f"Could not fetch regions: {exc}")

    @app.command("/zones")
    async def cmd_zones(ack, body, respond):
        await ack()
        parts = _parse_args(body.get("text", ""))
        region_id = _arg(parts, 0)
        if not region_id:
            await respond("Usage: `/zones <region_id>`\nExample: `/zones sf-bay`")
            return
        try:
            result = _tools.list_zones(region_id)
            await respond(format_zones(result, region_id))
        except ValueError as exc:
            await respond(str(exc))
        except Exception as exc:
            _log.exception("slack /zones failed")
            await respond(f"Could not fetch zones: {exc}")

    @app.command("/profiles")
    async def cmd_profiles(ack, respond):
        await ack()
        try:
            result = _tools.list_profiles()
            await respond(format_profiles(result))
        except Exception as exc:
            _log.exception("slack /profiles failed")
            await respond(f"Could not fetch profiles: {exc}")

    @app.command("/forecast")
    async def cmd_forecast(ack, body, respond):
        await ack()
        parts = _parse_args(body.get("text", ""))
        zone_id = _arg(parts, 0)
        profile_id = _arg(parts, 1, default="cruiser")
        if not zone_id:
            await respond(
                "Usage: `/forecast <zone_id> [profile_id]`\n"
                "Example: `/forecast city-front racer`"
            )
            return
        await respond(f"Fetching forecast for {zone_id}…")
        try:
            fc = _tools.get_zone_forecast(zone_id=zone_id, profile_id=profile_id, days=3, summary=True)
            await respond(format_forecast(fc))
        except ValueError as exc:
            await respond(str(exc))
        except Exception as exc:
            _log.exception("slack /forecast failed")
            await respond(f"Could not fetch forecast: {exc}")

    @app.command("/compare")
    async def cmd_compare(ack, body, respond):
        await ack()
        parts = _parse_args(body.get("text", ""))
        region_id = _arg(parts, 0)
        profile_id = _arg(parts, 1, default="cruiser")
        if not region_id:
            await respond(
                "Usage: `/compare <region_id> [profile_id]`\n"
                "Example: `/compare sf-bay cruiser`"
            )
            return
        await respond(f"Comparing zones in {region_id}…")
        try:
            ranked = _tools.compare_zones_in_region(region_id=region_id, profile_id=profile_id)
            warnings = _tools.get_active_warnings(region_id)
            text = format_compare(ranked, region_id)
            if warnings:
                from app.bot.slack_formatters import _warnings_block
                text += "\n" + _warnings_block(warnings)
            await respond(text)
        except ValueError as exc:
            await respond(str(exc))
        except Exception as exc:
            _log.exception("slack /compare failed")
            await respond(f"Could not compare zones: {exc}")

    @app.command("/windows")
    async def cmd_windows(ack, body, respond):
        await ack()
        parts = _parse_args(body.get("text", ""))
        zone_id = _arg(parts, 0)
        profile_id = _arg(parts, 1, default="cruiser")
        if not zone_id:
            await respond(
                "Usage: `/windows <zone_id> [profile_id]`\n"
                "Example: `/windows shilshole`"
            )
            return
        await respond(f"Finding best windows for {zone_id}…")
        try:
            windows = _tools.best_sail_windows(zone_id=zone_id, profile_id=profile_id, days=3, top_n=3)
            await respond(format_windows(windows, zone_id))
        except ValueError as exc:
            await respond(str(exc))
        except Exception as exc:
            _log.exception("slack /windows failed")
            await respond(f"Could not fetch windows: {exc}")

    @app.command("/warnings")
    async def cmd_warnings(ack, body, respond):
        await ack()
        parts = _parse_args(body.get("text", ""))
        region_id = _arg(parts, 0)
        if not region_id:
            await respond(
                "Usage: `/warnings <region_id>`\n"
                "Example: `/warnings sf-bay`"
            )
            return
        try:
            warnings = _tools.get_active_warnings(region_id)
            await respond(format_warnings(warnings, region_id))
        except ValueError as exc:
            await respond(str(exc))
        except Exception as exc:
            _log.exception("slack /warnings failed")
            await respond(f"Could not fetch warnings: {exc}")

    @app.command("/explain")
    async def cmd_explain(ack, body, respond):
        await ack()
        parts = _parse_args(body.get("text", ""))
        zone_id = _arg(parts, 0)
        profile_id = _arg(parts, 1, default="cruiser")
        if not zone_id:
            await respond(
                "Usage: `/explain <zone_id> [profile_id]`\n"
                "Example: `/explain city-front`"
            )
            return
        await respond(f"Explaining score for {zone_id}…")
        try:
            explanation = _tools.explain_score(zone_id=zone_id, profile_id=profile_id)
            await respond(format_explain(explanation, zone_id))
        except ValueError as exc:
            await respond(str(exc))
        except Exception as exc:
            _log.exception("slack /explain failed")
            await respond(f"Could not explain score: {exc}")

    @app.command("/reset")
    async def cmd_reset(ack, body, respond):
        await ack()
        user_id = body.get("user_id", "")
        if user_id:
            reset_history(_slack_uid(user_id))
        await respond("Conversation history cleared. What would you like to know?")

    # ── Natural-language: channel @-mentions ────────────────────────────────

    @app.event("app_mention")
    async def handle_mention(event, say):
        user_id = event.get("user", "")
        raw_text = event.get("text", "")
        text = _strip_mention(raw_text)
        if not text or not user_id:
            return
        await _run_nl_agent(user_id, text, say)

    # ── Natural-language: direct messages ───────────────────────────────────

    @app.event("message")
    async def handle_message(event, say):
        # Only handle DMs; skip bot messages and message subtypes (edits, deletes)
        if event.get("channel_type") != "im":
            return
        if event.get("subtype") or event.get("bot_id"):
            return
        user_id = event.get("user", "")
        text = event.get("text", "").strip()
        if not text or not user_id:
            return
        await _run_nl_agent(user_id, text, say)


# ---------------------------------------------------------------------------
# Shared NL agent runner
# ---------------------------------------------------------------------------

async def _run_nl_agent(user_id: str, text: str, say) -> None:
    """Run the OpenRouter agent for a user message and post the reply."""
    try:
        reply = await asyncio.to_thread(run_agent, _slack_uid(user_id), text)
    except RuntimeError as exc:
        _log.warning("Slack agent unavailable: %s", exc)
        await say(
            "The AI agent is not configured yet.\n\n"
            "Ask your admin to set `OPENROUTER_API_KEY`, or use slash commands:\n"
            "`/compare sf-bay` — rank all SF Bay zones\n"
            "`/forecast city-front` — forecast for a zone\n"
            "`/warnings sf-bay` — active marine warnings"
        )
        return
    except Exception as exc:
        _log.exception("Slack agent error for user %s", user_id)
        await say(
            f"Something went wrong while fetching your answer: {exc}\n"
            "Please try again or use a slash command like `/compare sf-bay`."
        )
        return
    await say(reply)
