"""Natural-language agent for the California Sail Telegram bot.

Connects to OpenRouter (OpenAI-compatible API) and uses the 8 existing
app.mcp.tools functions as callable tools so the LLM can answer sailing
questions in plain English.

Usage
-----
The agent is driven by :func:`run_agent`.  It is synchronous and should be
called from an async Telegram handler via ``asyncio.to_thread``.

Conversation history is kept in-memory per Telegram user ID, with a
configurable sliding-window size and idle TTL.  Call :func:`reset_history`
to clear a specific user's context (e.g. from a ``/reset`` command).

Configuration (environment variables)
--------------------------------------
OPENROUTER_API_KEY   Required.  Key from https://openrouter.ai
OPENROUTER_MODEL     Model slug (default: anthropic/claude-3-haiku)
AGENT_MAX_HISTORY    Max messages per user history window (default: 20)
AGENT_TTL_MINUTES    Idle minutes before history expires (default: 30)
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import app.mcp.tools as _tools

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "anthropic/claude-3-haiku"
_MAX_TOOL_ROUNDS = 8  # guard against runaway loops


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are California Sail, a friendly sailing-conditions assistant for three \
regions: San Francisco Bay (sf-bay), Puget Sound / Seattle (puget-sound), \
and Sardinia (sardinia).

You have access to live forecast tools. Use them to answer the user's \
questions accurately.

Guidelines:
- Always call get_active_warnings when giving safety-sensitive advice or \
  recommending a sail plan for a US region.
- Use compare_zones_in_region to rank zones when the user asks where to sail \
  in a region without specifying a zone.
- Use best_sail_windows when the user asks about timing or "when to go".
- Use explain_score when the user asks why a score is what it is.
- Be concise — Telegram messages have a 4096-character limit. Prefer brief \
  prose with the most important numbers inline.
- Never output raw JSON or Python dicts. Summarise tool results in natural \
  language.
- When mentioning sailability scores, always include the verdict \
  (GO / MAYBE / NO-GO).
- If a location or zone is outside the three supported regions, say so \
  clearly and list the available regions.
- Available sailor profiles: school, cruiser (default), racer.
"""

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_regions",
            "description": "List all available sailing regions (id, name, country, n_zones).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_zones",
            "description": "List all sailing zones within a region.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region_id": {
                        "type": "string",
                        "description": 'Region identifier, e.g. "sf-bay", "puget-sound", "sardinia".',
                    }
                },
                "required": ["region_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_profiles",
            "description": "List all available sailor profiles with scoring thresholds.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_zone_forecast",
            "description": (
                "Fetch and score the sailing forecast for a single zone. "
                "Returns current sailability, verdict, best windows, and daily summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_id": {
                        "type": "string",
                        "description": 'Zone identifier, e.g. "city-front", "shilshole", "alghero".',
                    },
                    "profile_id": {
                        "type": "string",
                        "description": 'Sailor profile: "school", "cruiser" (default), or "racer".',
                        "default": "cruiser",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Forecast horizon in days (1-7, default 3).",
                        "default": 3,
                    },
                    "summary": {
                        "type": "boolean",
                        "description": "True (default) = compact response without per-hour rows.",
                        "default": True,
                    },
                },
                "required": ["zone_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_zones_in_region",
            "description": (
                "Compare all zones in a region and rank by current sailability. "
                "Use this when the user asks where to sail in a region."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region_id": {
                        "type": "string",
                        "description": 'Region identifier, e.g. "sf-bay".',
                    },
                    "profile_id": {
                        "type": "string",
                        "description": 'Sailor profile (default "cruiser").',
                        "default": "cruiser",
                    },
                },
                "required": ["region_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "best_sail_windows",
            "description": (
                "Find the top sustained sailing windows for a zone. "
                "Use when the user asks about timing or 'when to go'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_id": {
                        "type": "string",
                        "description": "Zone identifier.",
                    },
                    "profile_id": {
                        "type": "string",
                        "description": 'Sailor profile (default "cruiser").',
                        "default": "cruiser",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Forecast horizon in days (1-7, default 3).",
                        "default": 3,
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Maximum windows to return (default 3).",
                        "default": 3,
                    },
                },
                "required": ["zone_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_warnings",
            "description": (
                "Return active NOAA marine warnings for a US region. "
                "Returns an empty list for non-US regions or when no warnings are active. "
                "Always call this for SF Bay or Puget Sound before recommending a sail plan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region_id": {
                        "type": "string",
                        "description": 'Region identifier, e.g. "sf-bay", "puget-sound".',
                    }
                },
                "required": ["region_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_score",
            "description": (
                "Explain the sailability score for a specific hour in a zone, "
                "with component breakdown and a plain-language summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_id": {
                        "type": "string",
                        "description": "Zone identifier.",
                    },
                    "hour_offset": {
                        "type": "integer",
                        "description": "Hour index into forecast (0 = now, default 0).",
                        "default": 0,
                    },
                    "profile_id": {
                        "type": "string",
                        "description": 'Sailor profile (default "cruiser").',
                        "default": "cruiser",
                    },
                },
                "required": ["zone_id"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool dispatcher — calls app.mcp.tools in-process
# ---------------------------------------------------------------------------

_TOOL_FN: dict[str, Any] = {
    "list_regions": _tools.list_regions,
    "list_zones": _tools.list_zones,
    "list_profiles": _tools.list_profiles,
    "get_zone_forecast": _tools.get_zone_forecast,
    "compare_zones_in_region": _tools.compare_zones_in_region,
    "best_sail_windows": _tools.best_sail_windows,
    "get_active_warnings": _tools.get_active_warnings,
    "explain_score": _tools.explain_score,
}


def _dispatch(name: str, arguments: str) -> str:
    """Call the named tool with JSON-decoded arguments and return a JSON string."""
    fn = _TOOL_FN.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        kwargs = json.loads(arguments) if arguments else {}
        result = fn(**kwargs)
        return json.dumps(result, default=str)
    except Exception as exc:
        _log.warning("Tool %s raised: %s", name, exc)
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Conversation history store
# ---------------------------------------------------------------------------

class ConversationStore:
    """In-memory per-user message history with sliding window and idle TTL."""

    def __init__(self, max_messages: int = 20, ttl_minutes: int = 30) -> None:
        self._max = max_messages
        self._ttl = ttl_minutes * 60  # seconds
        self._histories: dict[int, list[dict[str, Any]]] = {}
        self._last_access: dict[int, float] = {}

    def get(self, user_id: int) -> list[dict[str, Any]]:
        self._evict_expired()
        self._last_access[user_id] = time.monotonic()
        return self._histories.setdefault(user_id, [])

    def append(self, user_id: int, message: dict[str, Any]) -> None:
        history = self.get(user_id)
        history.append(message)
        # Keep only the last _max messages, always preserving the system prompt
        # which is injected separately — so the window covers user/assistant turns.
        if len(history) > self._max:
            del history[: len(history) - self._max]

    def reset(self, user_id: int) -> None:
        self._histories.pop(user_id, None)
        self._last_access.pop(user_id, None)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [uid for uid, t in self._last_access.items() if now - t > self._ttl]
        for uid in expired:
            self._histories.pop(uid, None)
            self._last_access.pop(uid, None)


# Module-level store — shared across all Telegram updates in one process.
_store = ConversationStore(
    max_messages=_cfg_int("AGENT_MAX_HISTORY", 20),
    ttl_minutes=_cfg_int("AGENT_TTL_MINUTES", 30),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reset_history(user_id: int) -> None:
    """Clear the conversation history for a specific Telegram user."""
    _store.reset(user_id)


def run_agent(user_id: int, user_text: str) -> str:
    """Run the agentic conversation loop for one user turn.

    Appends the user message to the per-user history, calls OpenRouter with
    all 8 tool schemas, executes any tool calls in-process, and returns the
    final assistant reply as a plain string (not MarkdownV2-escaped — the
    LLM is instructed to write plain Telegram-friendly prose).

    Raises
    ------
    RuntimeError
        If OPENROUTER_API_KEY is not set.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. "
            "Add it to your .env file to enable natural-language conversations."
        )

    model = os.environ.get("OPENROUTER_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL

    # Lazy import so the openai package is only required when the agent is used.
    from openai import OpenAI  # noqa: PLC0415

    client = OpenAI(api_key=api_key, base_url=_OPENROUTER_BASE_URL)

    # Append user turn to history
    _store.append(user_id, {"role": "user", "content": user_text})

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *_store.get(user_id),
    ]

    # Agentic loop — iterate until the model returns a plain text response or
    # we hit the guard limit.
    for round_num in range(_MAX_TOOL_ROUNDS):
        _log.debug("Agent round %d for user %d, model=%s", round_num, user_id, model)

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )

        choice = response.choices[0]
        assistant_msg = choice.message

        # Add the assistant's (possibly partial) message to the working list.
        messages.append(assistant_msg.model_dump(exclude_none=True))

        if not assistant_msg.tool_calls:
            # Final text reply — persist to history and return.
            reply = (assistant_msg.content or "").strip()
            _store.append(user_id, {"role": "assistant", "content": reply})
            return reply

        # Execute each tool call and append results.
        for tc in assistant_msg.tool_calls:
            tool_result = _dispatch(tc.function.name, tc.function.arguments)
            _log.debug("Tool %s → %s…", tc.function.name, tool_result[:120])
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                }
            )

    # Safety fallback — should not normally be reached.
    _log.warning("Agent hit max tool rounds (%d) for user %d", _MAX_TOOL_ROUNDS, user_id)
    return (
        "I ran into an issue fetching all the data I needed. "
        "Please try again or use a slash command like /compare sf-bay."
    )
