# Integrations

This document covers all four external integration surfaces: the MCP server, the Telegram bot, the Slack bot, and the OpenRouter natural-language agent.

---

## 1. MCP server

The Model Context Protocol (MCP) server exposes sailing conditions as callable tools to any MCP-compatible AI agent (Cursor, Claude Desktop, custom bots).

### Architecture

```
AI agent (Cursor / Claude Desktop / custom)
        │
        │  JSON-RPC over stdio  OR  HTTP/SSE
        ▼
app/mcp/server.py  (FastMCP instance)
        │
        ▼
app/mcp/tools.py   (8 tool functions)
        │
        ▼
app/services/forecast_service.py + region_service.py
        │
        ▼
External weather APIs (Open-Meteo, NOAA)
```

### Transports

| Transport | When to use | Command |
|---|---|---|
| `stdio` | Cursor, Claude Desktop — local process | `python -m app.mcp.server` |
| `sse` | Remote agents, deployed API | `python -m app.mcp.server --transport sse --port 8765` |

In production the SSE transport is served at `https://california-sail-api-<hash>-uw.a.run.app/mcp/sse` via the FastAPI mount in `app/api/main.py`.

### Available tools

| Tool | Required params | Optional | Returns |
|---|---|---|---|
| `list_regions` | — | — | List of regions with zone count |
| `list_zones` | `region_id` | — | List of zones in the region |
| `list_profiles` | — | — | List of sailor profiles with thresholds |
| `get_zone_forecast` | `zone_id` | `profile_id`, `days`, `summary` | Full or summary forecast dict |
| `compare_zones_in_region` | `region_id` | `profile_id`, `days` | Zones ranked by score |
| `best_sail_windows` | `zone_id` | `profile_id`, `days`, `window_hours`, `top_n` | Top N sailing windows |
| `get_active_warnings` | `region_id` | — | Active marine warnings |
| `explain_score` | `zone_id`, `hour_index` | `profile_id` | Per-component score breakdown |

All tools return JSON-safe Python dicts (no numpy types, no DataFrames).

### Connecting Cursor

1. Copy `examples/mcp/cursor.json` to your Cursor MCP config location (usually `~/.cursor/mcp.json` or set in Cursor settings).
2. Replace `/path/to/california_sail` with the actual repo path.

```json
{
  "mcpServers": {
    "california-sail": {
      "command": "/path/to/california_sail/.venv/bin/python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/california_sail",
      "env": {
        "PYTHONPATH": "/path/to/california_sail"
      }
    }
  }
}
```

> The `PYTHONPATH` env var is required because Cursor spawns the subprocess without inheriting the shell `PYTHONPATH`.

### Connecting Claude Desktop

Same config as Cursor. Copy `examples/mcp/claude_desktop.json` to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).

### Tool output example

```python
# list_regions()
[
  {"id": "sf-bay", "name": "San Francisco Bay", "country": "US", "zone_count": 8},
  {"id": "puget-sound", "name": "Puget Sound (Seattle)", "country": "US", "zone_count": 7},
  {"id": "sardinia", "name": "Sardinia", "country": "IT", "zone_count": 9},
]

# get_zone_forecast("city-front", summary=True)
{
  "zone": {"id": "city-front", "name": "City Front", ...},
  "profile": {"id": "cruiser", ...},
  "verdict": "GO",
  "avg_score": 72.4,
  "best_windows": [...],
  "warnings": [],
  "fetched_at": "2026-05-14T10:00:00Z",
}
```

### Caching in the MCP server

The MCP server (and the bots) use `TTLForecastCache` — a thread-safe in-process cache with a 15-minute TTL (`CACHE_TTL_SECONDS` in `.env`). This avoids hammering the free APIs when multiple agents query the same zone in quick succession.

---

## 2. Telegram bot

### Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) on Telegram. Copy the token.
2. Set `TELEGRAM_BOT_TOKEN` in `.env` (or Secret Manager for production).

### Local development (polling)

```bash
python -m app.bot.telegram
```

The bot polls Telegram's servers every few seconds. No public URL needed.

### Production (webhook)

When `WEBHOOK_URL` is set, `app/api/main.py`'s lifespan function automatically registers the webhook at startup:

```
POST https://api.telegram.org/bot<TOKEN>/setWebhook
  url = WEBHOOK_URL + "/telegram/webhook"
```

Telegram then pushes updates to the API service.

### Command reference

| Command | Description | Example |
|---|---|---|
| `/start` | Welcome message | `/start` |
| `/help` | Show all commands | `/help` |
| `/regions` | List all regions | `/regions` |
| `/zones <region_id>` | List zones in a region | `/zones sf-bay` |
| `/profiles` | List sailor profiles | `/profiles` |
| `/forecast <zone_id> [profile_id] [days]` | Zone forecast | `/forecast city-front racer 3` |
| `/compare <region_id> [profile_id]` | Compare all zones in a region | `/compare sardinia cruiser` |
| `/windows <zone_id> [profile_id]` | Best sailing windows | `/windows costa-smeralda` |
| `/warnings <region_id>` | Active marine warnings | `/warnings sf-bay` |
| `/explain <zone_id> <hour_index>` | Score breakdown for a specific hour | `/explain city-front 6` |

### Natural language mode

Any plain-text message (not a command) is forwarded to the **NL agent** (`app/bot/agent.py`). The agent uses OpenRouter to interpret the question, calls the relevant MCP tools, and replies in natural language.

Example conversation:

```
User:  What's the best place to sail around San Francisco Bay this afternoon?
Bot:   Based on current conditions, Raccoon Strait scores 78 (GO) with 14 kt
       NW wind and 0.8 m waves. City Front also looks good at 71 (GO) but
       expect some chop near the Gate on the ebb.
```

The agent maintains per-user conversation history (up to `AGENT_MAX_HISTORY` messages, evicted after `AGENT_TTL_MINUTES`).

### Message formatting

The Telegram bot uses [MarkdownV2](https://core.telegram.org/bots/api#markdownv2-style). All text is passed through `_esc()` in `app/bot/formatters.py` before sending. Hyphens in zone IDs are escaped to `\-`.

---

## 3. Slack bot

### Setup

1. Create a Slack app at https://api.slack.com/apps.
2. Enable **Slash Commands** and **Event Subscriptions**.
3. Add the following slash commands (all pointing to `<API_URL>/slack/events`):
   - `/sail-regions`, `/sail-zones`, `/sail-profiles`, `/sail-forecast`, `/sail-compare`, `/sail-windows`, `/sail-warnings`, `/sail-explain`
4. Subscribe to the `app_mention` event.
5. Set `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` in `.env` / Secret Manager.

### Slash commands

The Slack commands mirror the Telegram commands. They are handled by `app/bot/slack.py`.

| Command | Equivalent Telegram | Notes |
|---|---|---|
| `/sail-regions` | `/regions` | — |
| `/sail-zones <region_id>` | `/zones` | — |
| `/sail-profiles` | `/profiles` | — |
| `/sail-forecast <zone_id> [...]` | `/forecast` | — |
| `/sail-compare <region_id> [...]` | `/compare` | — |
| `/sail-windows <zone_id> [...]` | `/windows` | — |
| `/sail-warnings <region_id>` | `/warnings` | — |
| `/sail-explain <zone_id> <hour>` | `/explain` | — |

### Natural language via app_mention

Mentioning the bot in a channel triggers the NL agent:

```
@california-sail what are the best sailing conditions in Sardinia tomorrow?
```

The conversation history is keyed by `<team_id>:<user_id>` hash and is shared across channels for the same user.

### Message formatting

Slack uses its own [mrkdwn](https://api.slack.com/reference/surfaces/formatting) syntax. The `app/bot/slack_formatters.py` module mirrors `formatters.py` but uses Slack-specific markup (`*bold*`, backtick code spans, `<URL|label>` links).

---

## 4. OpenRouter NL agent

### Overview

The NL agent (`app/bot/agent.py`) is a simple tool-calling loop on top of any OpenAI-compatible API. It uses OpenRouter to access a range of models without managing individual API keys.

```
User message
     │
     ▼
ConversationStore.add(user_id, "user", message)
     │
     ▼
openai.chat.completions.create(
    model=OPENROUTER_MODEL,
    messages=history,
    tools=TOOL_SCHEMAS
)
     │
     ├── model responds with tool_calls?
     │         │
     │         ▼
     │   _dispatch(tool_name, args)   ← calls app.mcp.tools.*
     │         │
     │         ▼
     │   append tool result to history
     │         │
     │         └── loop back to create()
     │
     └── model responds with text?
               │
               ▼
         return reply to bot handler
```

### Configuration

| Env var | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Required for NL mode |
| `OPENROUTER_MODEL` | `anthropic/claude-3-haiku` | Any model on OpenRouter |
| `AGENT_MAX_HISTORY` | 20 | Max messages to keep per user |
| `AGENT_TTL_MINUTES` | 30 | Conversation eviction timeout |

### Tool schemas

`TOOL_SCHEMAS` in `agent.py` is a list of JSON Schema objects describing all 8 MCP tools. These are passed to the model as the `tools=` parameter, allowing it to decide which tools to call based on the user's question.

When extending the MCP tool surface with new tools, `TOOL_SCHEMAS` must be updated to match.

### Conversation isolation

Each user has an independent conversation history in `ConversationStore`. Conversations are evicted automatically after `AGENT_TTL_MINUTES` of inactivity. The store is process-local (in-memory) — it resets on service restart.

---

## 5. Adding a new integration

To add a new messaging channel (e.g. WhatsApp, Discord):

1. Create `app/bot/<channel>.py` with command/event handlers.
2. Call `app.mcp.tools.*` directly for structured commands.
3. Call `app.bot.agent.run_agent(user_id, message)` for NL messages.
4. Create `app/bot/<channel>_formatters.py` with output formatters for the channel's markup syntax.
5. Register the webhook endpoint in `app/api/main.py`.
6. Add tests in `tests/test_<channel>_formatters.py`.
