"""California Sail Telegram bot — command handlers and entry points.

Commands
--------
/start                     Welcome message and command list
/regions                   List all sailing regions
/zones <region_id>         List zones in a region
/profiles                  List sailor profiles
/forecast <zone_id>        Current forecast for a zone (cruiser profile)
/forecast <zone_id> <profile_id>  Forecast with a specific profile
/compare <region_id>       Rank all zones in a region
/compare <region_id> <profile_id>  Rank with a specific profile
/windows <zone_id>         Best sailing windows in a zone
/warnings <region_id>      Active NOAA marine warnings
/explain <zone_id>         Score breakdown for the next hour
/reset                     Clear your conversation history with the AI agent

Natural language
----------------
Any plain-text message (not starting with /) is routed to the AI agent,
which uses OpenRouter to understand the question and calls the forecast
tools automatically.  Set OPENROUTER_API_KEY and OPENROUTER_MODEL in .env.

Run modes
---------
Polling (local dev, no public endpoint needed):
    python -m app.bot.telegram

Webhook (started by app/api/main.py via the Telegram Application):
    Use the Application object exported from this module.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

import app.mcp.tools as _tools
from app.bot.agent import reset_history, run_agent
from app.bot.formatters import (
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

_MAX_MSG = 4096  # Telegram message length limit


async def _reply(update: Update, text: str) -> None:
    """Send a MarkdownV2 reply, splitting if over the Telegram limit."""
    if not text:
        return
    chat = update.effective_chat
    if chat is None:
        return
    # Split on newlines if too long
    while len(text) > _MAX_MSG:
        split_at = text.rfind("\n", 0, _MAX_MSG)
        if split_at == -1:
            split_at = _MAX_MSG
        await chat.send_message(text[:split_at], parse_mode="MarkdownV2")
        text = text[split_at:].lstrip("\n")
    if text:
        await chat.send_message(text, parse_mode="MarkdownV2")


async def _reply_error(update: Update, message: str) -> None:
    chat = update.effective_chat
    if chat:
        await chat.send_message(message)


def _arg(context: ContextTypes.DEFAULT_TYPE, index: int, default: str = "") -> str:
    args = context.args or []
    return args[index] if index < len(args) else default


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message."""
    text = (
        "⛵ *California Sail* — live sailing conditions\n\n"
        "Just ask me anything in plain English — for example:\n"
        "_Where should I sail in SF Bay today?_\n"
        "_When are the best windows at Shilshole this weekend?_\n"
        "_Is it safe to take beginners out in Sardinia?_\n\n"
        "Or use a slash command for instant results:\n"
        "/regions — list all regions\n"
        "/zones sf\\-bay — list zones in a region\n"
        "/compare sf\\-bay — rank zones by sailability\n"
        "/forecast city\\-front — forecast for a zone\n"
        "/windows city\\-front — best sailing windows\n"
        "/warnings sf\\-bay — active marine warnings\n"
        "/explain city\\-front — score breakdown\n"
        "/profiles — list sailor profiles\n"
        "/reset — clear conversation history\n\n"
        "Regions: `sf-bay` \\| `puget-sound` \\| `sardinia`\n"
        "Profiles: `school` \\| `cruiser` \\| `racer`"
    )
    await _reply(update, text)


async def cmd_regions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/regions — list all regions."""
    try:
        regions = _tools.list_regions()
        await _reply(update, format_regions(regions))
    except Exception as exc:
        _log.exception("cmd_regions failed")
        await _reply_error(update, f"Could not fetch regions: {exc}")


async def cmd_zones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/zones <region_id>"""
    region_id = _arg(context, 0)
    if not region_id:
        await _reply_error(update, "Usage: /zones <region_id>\nExample: /zones sf-bay")
        return
    try:
        zones = _tools.list_zones(region_id)
        await _reply(update, format_zones(zones, region_id))
    except ValueError as exc:
        await _reply_error(update, str(exc))
    except Exception as exc:
        _log.exception("cmd_zones failed")
        await _reply_error(update, f"Could not fetch zones: {exc}")


async def cmd_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/profiles — list all sailor profiles."""
    try:
        profiles = _tools.list_profiles()
        await _reply(update, format_profiles(profiles))
    except Exception as exc:
        _log.exception("cmd_profiles failed")
        await _reply_error(update, f"Could not fetch profiles: {exc}")


async def cmd_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/forecast <zone_id> [profile_id]"""
    zone_id = _arg(context, 0)
    profile_id = _arg(context, 1, default="cruiser")
    if not zone_id:
        await _reply_error(update, "Usage: /forecast <zone_id> [profile_id]\nExample: /forecast city-front racer")
        return
    chat = update.effective_chat
    if chat:
        await chat.send_message(f"Fetching forecast for {zone_id}…")
    try:
        fc = _tools.get_zone_forecast(zone_id=zone_id, profile_id=profile_id, days=3, summary=True)
        await _reply(update, format_forecast(fc))
    except ValueError as exc:
        await _reply_error(update, str(exc))
    except Exception as exc:
        _log.exception("cmd_forecast failed")
        await _reply_error(update, f"Could not fetch forecast: {exc}")


async def cmd_compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/compare <region_id> [profile_id]"""
    region_id = _arg(context, 0)
    profile_id = _arg(context, 1, default="cruiser")
    if not region_id:
        await _reply_error(update, "Usage: /compare <region_id> [profile_id]\nExample: /compare sf-bay cruiser")
        return
    chat = update.effective_chat
    if chat:
        await chat.send_message(f"Comparing zones in {region_id}…")
    try:
        ranked = _tools.compare_zones_in_region(region_id=region_id, profile_id=profile_id)
        warnings = _tools.get_active_warnings(region_id)
        text = format_compare(ranked, region_id)
        if warnings:
            from app.bot.formatters import _warnings_block
            text += "\n" + _warnings_block(warnings)
        await _reply(update, text)
    except ValueError as exc:
        await _reply_error(update, str(exc))
    except Exception as exc:
        _log.exception("cmd_compare failed")
        await _reply_error(update, f"Could not compare zones: {exc}")


async def cmd_windows(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/windows <zone_id> [profile_id]"""
    zone_id = _arg(context, 0)
    profile_id = _arg(context, 1, default="cruiser")
    if not zone_id:
        await _reply_error(update, "Usage: /windows <zone_id> [profile_id]\nExample: /windows shilshole")
        return
    chat = update.effective_chat
    if chat:
        await chat.send_message(f"Finding best windows for {zone_id}…")
    try:
        windows = _tools.best_sail_windows(zone_id=zone_id, profile_id=profile_id, days=3, top_n=3)
        await _reply(update, format_windows(windows, zone_id))
    except ValueError as exc:
        await _reply_error(update, str(exc))
    except Exception as exc:
        _log.exception("cmd_windows failed")
        await _reply_error(update, f"Could not fetch windows: {exc}")


async def cmd_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/warnings <region_id>"""
    region_id = _arg(context, 0)
    if not region_id:
        await _reply_error(update, "Usage: /warnings <region_id>\nExample: /warnings sf-bay")
        return
    try:
        warnings = _tools.get_active_warnings(region_id)
        await _reply(update, format_warnings(warnings, region_id))
    except ValueError as exc:
        await _reply_error(update, str(exc))
    except Exception as exc:
        _log.exception("cmd_warnings failed")
        await _reply_error(update, f"Could not fetch warnings: {exc}")


async def cmd_explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/explain <zone_id> [profile_id]"""
    zone_id = _arg(context, 0)
    profile_id = _arg(context, 1, default="cruiser")
    if not zone_id:
        await _reply_error(update, "Usage: /explain <zone_id> [profile_id]\nExample: /explain city-front")
        return
    chat = update.effective_chat
    if chat:
        await chat.send_message(f"Explaining score for {zone_id}…")
    try:
        explanation = _tools.explain_score(zone_id=zone_id, profile_id=profile_id)
        await _reply(update, format_explain(explanation, zone_id))
    except ValueError as exc:
        await _reply_error(update, str(exc))
    except Exception as exc:
        _log.exception("cmd_explain failed")
        await _reply_error(update, f"Could not explain score: {exc}")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reset — clear conversation history for this user."""
    user = update.effective_user
    if user:
        reset_history(user.id)
    chat = update.effective_chat
    if chat:
        await chat.send_message("Conversation history cleared. What would you like to know?")


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all for unrecognised commands."""
    await _reply_error(
        update,
        "I don't know that command. Send /start to see the full command list.",
    )


async def msg_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route plain-text messages to the AI agent (falls back to help text if no API key)."""
    user = update.effective_user
    text = update.message.text if update.message else None
    if not text or not user:
        return

    chat = update.effective_chat
    if not chat:
        return

    # Show a typing indicator while the agent works.
    await chat.send_action("typing")

    try:
        reply = await asyncio.to_thread(run_agent, user.id, text)
    except RuntimeError as exc:
        # OPENROUTER_API_KEY not set — give a helpful nudge.
        _log.warning("Agent unavailable: %s", exc)
        await chat.send_message(
            "The AI agent is not configured yet.\n\n"
            "Ask your admin to set OPENROUTER_API_KEY, or use slash commands:\n\n"
            "/compare sf-bay — rank all SF Bay zones\n"
            "/forecast city-front — forecast for a zone\n"
            "/warnings sf-bay — active marine warnings\n"
            "/windows shilshole — best sailing windows\n\n"
            "Send /start for the full list."
        )
        return
    except Exception as exc:
        _log.exception("Agent error for user %d", user.id)
        await chat.send_message(
            f"Something went wrong while fetching your answer: {exc}\n"
            "Please try again, or use a slash command like /compare sf-bay."
        )
        return

    await chat.send_message(reply)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def build_application(token: str) -> Application:
    """Build and return a configured Telegram Application."""
    from telegram.ext import MessageHandler, filters

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("regions", cmd_regions))
    app.add_handler(CommandHandler("zones", cmd_zones))
    app.add_handler(CommandHandler("profiles", cmd_profiles))
    app.add_handler(CommandHandler("forecast", cmd_forecast))
    app.add_handler(CommandHandler("compare", cmd_compare))
    app.add_handler(CommandHandler("windows", cmd_windows))
    app.add_handler(CommandHandler("warnings", cmd_warnings))
    app.add_handler(CommandHandler("explain", cmd_explain))
    app.add_handler(CommandHandler("reset", cmd_reset))
    # Catch-alls — must be registered last
    app.add_handler(CommandHandler("unknown", cmd_unknown))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_fallback))
    return app


# ---------------------------------------------------------------------------
# Entry point (polling mode for local dev)
# ---------------------------------------------------------------------------

def _get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Add it to your .env file or set the environment variable."
        )
    return token


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # Load .env automatically so the user doesn't need to `source .env` first
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(prog="python -m app.bot.telegram")
    parser.add_argument("--mode", choices=["polling"], default="polling",
                        help="Run mode (only 'polling' supported here; webhook is via app/api/main.py)")
    args = parser.parse_args()

    token = _get_token()
    application = build_application(token)
    _log.info("Starting California Sail bot in polling mode…")
    application.run_polling(drop_pending_updates=True)
