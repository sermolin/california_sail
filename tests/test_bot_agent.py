"""Unit tests for app/bot/agent.py.

All tests run fully offline:
- OpenRouter HTTP calls are patched via unittest.mock.
- app.mcp.tools functions are patched where needed.
- No OPENROUTER_API_KEY is required.
"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.bot.agent import (
    TOOL_SCHEMAS,
    ConversationStore,
    _dispatch,
    reset_history,
    run_agent,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal fake OpenAI response objects
# ---------------------------------------------------------------------------

def _make_text_response(content: str) -> MagicMock:
    """Simulate a plain-text (no tool call) chat completion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = []
    msg.model_dump.return_value = {"role": "assistant", "content": content}

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_tool_response(tool_name: str, arguments: dict, call_id: str = "tc1") -> MagicMock:
    """Simulate a response where the LLM requests one tool call."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(arguments)

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump.return_value = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "function": {"name": tool_name, "arguments": json.dumps(arguments)}}],
    }

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# ConversationStore
# ---------------------------------------------------------------------------

class TestConversationStore:
    def test_append_and_get(self):
        store = ConversationStore(max_messages=5, ttl_minutes=60)
        store.append(1, {"role": "user", "content": "hello"})
        history = store.get(1)
        assert len(history) == 1
        assert history[0]["content"] == "hello"

    def test_sliding_window(self):
        store = ConversationStore(max_messages=3, ttl_minutes=60)
        for i in range(5):
            store.append(1, {"role": "user", "content": str(i)})
        history = store.get(1)
        assert len(history) == 3
        assert history[0]["content"] == "2"
        assert history[-1]["content"] == "4"

    def test_reset_clears_history(self):
        store = ConversationStore(max_messages=10, ttl_minutes=60)
        store.append(42, {"role": "user", "content": "test"})
        store.reset(42)
        assert store.get(42) == []

    def test_reset_unknown_user_is_noop(self):
        store = ConversationStore(max_messages=10, ttl_minutes=60)
        store.reset(999)  # should not raise

    def test_ttl_eviction(self):
        store = ConversationStore(max_messages=10, ttl_minutes=1)
        store.append(7, {"role": "user", "content": "hi"})
        # Manually age the last-access timestamp past the TTL
        store._last_access[7] = time.monotonic() - 3600
        # Triggering get for a different user forces eviction
        store.get(8)
        assert 7 not in store._histories

    def test_separate_histories_per_user(self):
        store = ConversationStore(max_messages=10, ttl_minutes=60)
        store.append(1, {"role": "user", "content": "user one"})
        store.append(2, {"role": "user", "content": "user two"})
        assert store.get(1)[0]["content"] == "user one"
        assert store.get(2)[0]["content"] == "user two"


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_known_tool_returns_json(self):
        from app.bot import agent as _agent_mod
        orig = _agent_mod._TOOL_FN["list_regions"]
        _agent_mod._TOOL_FN["list_regions"] = lambda: [{"id": "sf-bay"}]
        try:
            result = _dispatch("list_regions", "{}")
        finally:
            _agent_mod._TOOL_FN["list_regions"] = orig
        assert json.loads(result) == [{"id": "sf-bay"}]

    def test_unknown_tool_returns_error(self):
        result = _dispatch("nonexistent_tool", "{}")
        parsed = json.loads(result)
        assert "error" in parsed

    def test_tool_exception_returns_error_json(self):
        from app.bot import agent as _agent_mod
        orig = _agent_mod._TOOL_FN["list_zones"]
        _agent_mod._TOOL_FN["list_zones"] = MagicMock(side_effect=ValueError("bad region"))
        try:
            result = _dispatch("list_zones", json.dumps({"region_id": "bad"}))
        finally:
            _agent_mod._TOOL_FN["list_zones"] = orig
        parsed = json.loads(result)
        assert "error" in parsed
        assert "bad region" in parsed["error"]

    def test_empty_arguments_string(self):
        from app.bot import agent as _agent_mod
        orig = _agent_mod._TOOL_FN["list_profiles"]
        _agent_mod._TOOL_FN["list_profiles"] = lambda: []
        try:
            result = _dispatch("list_profiles", "")
        finally:
            _agent_mod._TOOL_FN["list_profiles"] = orig
        assert json.loads(result) == []


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

class TestToolSchemas:
    def test_all_eight_tools_present(self):
        names = {s["function"]["name"] for s in TOOL_SCHEMAS}
        expected = {
            "list_regions", "list_zones", "list_profiles",
            "get_zone_forecast", "compare_zones_in_region",
            "best_sail_windows", "get_active_warnings", "explain_score",
        }
        assert names == expected

    def test_each_schema_has_required_fields(self):
        for schema in TOOL_SCHEMAS:
            assert schema["type"] == "function"
            fn = schema["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn


# ---------------------------------------------------------------------------
# run_agent — missing API key
# ---------------------------------------------------------------------------

class TestRunAgentNoKey:
    def test_raises_runtime_error_without_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            run_agent(user_id=1, user_text="Where should I sail?")


# ---------------------------------------------------------------------------
# run_agent — plain text response (no tool calls)
# ---------------------------------------------------------------------------

class TestRunAgentTextReply:
    def test_returns_assistant_content(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

        fake_response = _make_text_response("Sail at Raccoon Strait!")

        with patch("openai.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = fake_response
            MockOpenAI.return_value = mock_client

            reply = run_agent(user_id=100, user_text="Where should I sail?")

        assert reply == "Sail at Raccoon Strait!"

    def test_reply_stored_in_history(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

        reset_history(200)

        fake_response = _make_text_response("Go to Alghero!")

        with patch("openai.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = fake_response
            MockOpenAI.return_value = mock_client

            run_agent(user_id=200, user_text="Best zone in Sardinia?")

        from app.bot.agent import _store
        history = _store.get(200)
        roles = [m["role"] for m in history]
        assert "user" in roles
        assert "assistant" in roles


# ---------------------------------------------------------------------------
# run_agent — one tool call then text reply
# ---------------------------------------------------------------------------

class TestRunAgentToolCall:
    def test_tool_call_dispatched_and_result_sent_back(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

        from app.bot import agent as _agent_mod
        orig_compare = _agent_mod._TOOL_FN["compare_zones_in_region"]
        _agent_mod._TOOL_FN["compare_zones_in_region"] = lambda **kw: [
            {"zone_id": "city-front", "sailability": 75}
        ]

        tool_resp = _make_tool_response(
            "compare_zones_in_region", {"region_id": "sf-bay"}
        )
        text_resp = _make_text_response("City Front is best right now.")

        try:
            with patch("openai.OpenAI") as MockOpenAI:
                mock_client = MagicMock()
                mock_client.chat.completions.create.side_effect = [tool_resp, text_resp]
                MockOpenAI.return_value = mock_client

                reply = run_agent(user_id=300, user_text="Where should I sail in SF Bay?")
        finally:
            _agent_mod._TOOL_FN["compare_zones_in_region"] = orig_compare

        assert reply == "City Front is best right now."
        assert mock_client.chat.completions.create.call_count == 2

    def test_tool_result_included_in_second_request(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

        from app.bot import agent as _agent_mod
        orig_list = _agent_mod._TOOL_FN["list_regions"]
        _agent_mod._TOOL_FN["list_regions"] = lambda: [{"id": "sf-bay"}, {"id": "sardinia"}]

        tool_resp = _make_tool_response("list_regions", {})
        text_resp = _make_text_response("Three regions available.")

        try:
            with patch("openai.OpenAI") as MockOpenAI:
                mock_client = MagicMock()
                mock_client.chat.completions.create.side_effect = [tool_resp, text_resp]
                MockOpenAI.return_value = mock_client

                run_agent(user_id=301, user_text="What regions do you cover?")
        finally:
            _agent_mod._TOOL_FN["list_regions"] = orig_list

        second_call_messages = mock_client.chat.completions.create.call_args_list[1][1]["messages"]
        roles = [m["role"] for m in second_call_messages]
        assert "tool" in roles


# ---------------------------------------------------------------------------
# reset_history public function
# ---------------------------------------------------------------------------

class TestResetHistory:
    def test_reset_history_clears_store(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

        reset_history(500)
        fake_response = _make_text_response("Hello!")

        with patch("openai.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = fake_response
            MockOpenAI.return_value = mock_client
            run_agent(user_id=500, user_text="Hello")

        from app.bot.agent import _store
        assert len(_store.get(500)) > 0

        reset_history(500)
        assert _store.get(500) == []
