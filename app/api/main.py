"""California Sail — FastAPI service.

Exposes three capabilities in one ASGI process:
  GET  /health              — Cloud Run health check
  POST /telegram/webhook    — Telegram Bot API webhook receiver
  *    /mcp/*               — MCP SSE transport (FastMCP sse_app mounted)

Environment variables
---------------------
TELEGRAM_BOT_TOKEN   Required. The bot token from @BotFather.
WEBHOOK_URL          Optional. Full HTTPS URL of this service (e.g.
                     https://california-sail-api-xxxx-uw.a.run.app).
                     When set, the service registers the webhook with Telegram
                     on startup and deletes it on shutdown.
                     When absent, the webhook endpoint is registered but no
                     auto-registration happens (useful for local testing with
                     a tunnel or if you register the webhook manually).

Running locally (webhook mode is optional for local — use polling instead):
    uvicorn app.api.main:app --reload --port 8080

Running in production (Cloud Run):
    uvicorn app.api.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

# Load .env automatically (no-op if python-dotenv is not installed or .env absent)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, Request, Response, status
from telegram import Update

from app.bot.telegram import build_application
from app.mcp.server import mcp

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Telegram application (module-level singleton)
# ---------------------------------------------------------------------------

def _get_token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None


def _get_webhook_url() -> str | None:
    return os.environ.get("WEBHOOK_URL", "").strip() or None


_tg_app = None  # initialised in lifespan


# ---------------------------------------------------------------------------
# Lifespan: start/stop Telegram webhook registration
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _tg_app
    token = _get_token()
    if token:
        _tg_app = build_application(token)
        await _tg_app.initialize()

        webhook_url = _get_webhook_url()
        if webhook_url:
            full_url = f"{webhook_url.rstrip('/')}/telegram/webhook"
            _log.info("Registering Telegram webhook: %s", full_url)
            await _tg_app.bot.set_webhook(
                url=full_url,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )
        else:
            _log.warning(
                "WEBHOOK_URL not set — Telegram webhook not auto-registered. "
                "Bot will not receive updates unless you register it manually "
                "or run polling mode instead."
            )

        await _tg_app.start()
    else:
        _log.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled.")

    yield

    if _tg_app is not None:
        webhook_url = _get_webhook_url()
        if webhook_url:
            _log.info("Deleting Telegram webhook on shutdown")
            try:
                await _tg_app.bot.delete_webhook()
            except Exception:
                pass
        await _tg_app.stop()
        await _tg_app.shutdown()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="California Sail API",
    description="Telegram bot webhook + MCP SSE transport for California Sail",
    version="1.0.0",
    lifespan=_lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Cloud Run health check — always returns 200."""
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> Response:
    """Receive updates from Telegram and dispatch to command handlers."""
    if _tg_app is None:
        return Response(
            content="Bot not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    try:
        data = await request.json()
        update = Update.de_json(data, _tg_app.bot)
        await _tg_app.process_update(update)
    except Exception as exc:
        _log.exception("Error processing Telegram update: %s", exc)
    return Response(status_code=status.HTTP_200_OK)


# Mount the MCP SSE server at /mcp
# Agents connect to http://<host>/mcp/sse
app.mount("/mcp", mcp.sse_app())
