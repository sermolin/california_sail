"""Tests for app/bot/slack.py.

Tests cover:
- _slack_uid: deterministic, int result
- _parse_args / _arg helpers
- _strip_mention
- build_slack_handler: returns None when env vars absent
- build_slack_handler: returns handler when env vars present (mocked slack-bolt)
"""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.slack import (
    _arg,
    _parse_args,
    _slack_uid,
    _strip_mention,
    build_slack_handler,
)


# ---------------------------------------------------------------------------
# _slack_uid
# ---------------------------------------------------------------------------

class TestSlackUid:
    def test_returns_int(self):
        assert isinstance(_slack_uid("U0123456789"), int)

    def test_deterministic(self):
        assert _slack_uid("U0123456789") == _slack_uid("U0123456789")

    def test_different_users_different_ids(self):
        assert _slack_uid("U0000000001") != _slack_uid("U0000000002")

    def test_non_negative(self):
        for uid in ["U0000000000", "UABCDEFGH", "W123"]:
            assert _slack_uid(uid) >= 0

    def test_matches_md5(self):
        user = "U0123456789"
        expected = int(hashlib.md5(user.encode()).hexdigest()[:15], 16)
        assert _slack_uid(user) == expected


# ---------------------------------------------------------------------------
# _parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_empty_string(self):
        assert _parse_args("") == []

    def test_whitespace_only(self):
        assert _parse_args("   ") == []

    def test_none_equivalent(self):
        assert _parse_args(None) == []  # type: ignore[arg-type]

    def test_single_token(self):
        assert _parse_args("sf-bay") == ["sf-bay"]

    def test_two_tokens(self):
        assert _parse_args("city-front racer") == ["city-front", "racer"]

    def test_extra_whitespace(self):
        assert _parse_args("  sf-bay   cruiser  ") == ["sf-bay", "cruiser"]


class TestArg:
    def test_returns_token_at_index(self):
        assert _arg(["a", "b", "c"], 1) == "b"

    def test_returns_default_when_out_of_range(self):
        assert _arg(["a"], 5) == ""

    def test_custom_default(self):
        assert _arg([], 0, default="cruiser") == "cruiser"


# ---------------------------------------------------------------------------
# _strip_mention
# ---------------------------------------------------------------------------

class TestStripMention:
    def test_strips_leading_mention(self):
        assert _strip_mention("<@U0123456> hello there") == "hello there"

    def test_no_mention(self):
        assert _strip_mention("just a message") == "just a message"

    def test_empty_string(self):
        assert _strip_mention("") == ""

    def test_mention_only(self):
        assert _strip_mention("<@UABC123>") == ""

    def test_preserves_inner_mentions(self):
        result = _strip_mention("<@U000> tell me about <@U111>")
        assert result == "tell me about <@U111>"


# ---------------------------------------------------------------------------
# build_slack_handler — missing env vars
# ---------------------------------------------------------------------------

class TestBuildSlackHandlerMissingEnv:
    def test_returns_none_when_token_missing(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
        handler = build_slack_handler()
        assert handler is None

    def test_returns_none_when_only_token_set(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
        handler = build_slack_handler()
        assert handler is None

    def test_returns_none_when_only_secret_set(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.setenv("SLACK_SIGNING_SECRET", "secret123")
        handler = build_slack_handler()
        assert handler is None


# ---------------------------------------------------------------------------
# build_slack_handler — env vars present (mock slack-bolt)
# ---------------------------------------------------------------------------

class TestBuildSlackHandlerWithEnv:
    def test_returns_handler_when_both_vars_set(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_SIGNING_SECRET", "test-signing-secret")

        # AsyncApp initializes fine with any string token; signature
        # verification only happens at HTTP request time, not at build time.
        result = build_slack_handler()

        assert result is not None

    def test_handler_type(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_SIGNING_SECRET", "test-signing-secret")

        from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

        result = build_slack_handler()
        assert isinstance(result, AsyncSlackRequestHandler)
