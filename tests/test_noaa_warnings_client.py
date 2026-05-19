"""Tests for app/infra/noaa_warnings_client.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.infra.noaa_warnings_client import (
    InvalidNoaaWarningsResponseError,
    _validate_warnings_response,
    fetch_marine_warnings,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture() -> dict:
    return json.loads((FIXTURES / "noaa_warnings_response.json").read_text())


class TestValidateWarningsResponse:
    def test_valid_response_passes(self):
        _validate_warnings_response(_load_fixture())

    def test_wrong_type_raises(self):
        with pytest.raises(InvalidNoaaWarningsResponseError, match="FeatureCollection"):
            _validate_warnings_response({"type": "Feature"})

    def test_missing_features_raises(self):
        with pytest.raises(InvalidNoaaWarningsResponseError, match="features"):
            _validate_warnings_response({"type": "FeatureCollection"})


class TestFetchMarineWarnings:
    def test_returns_only_marine_warnings(self):
        with patch("app.infra.noaa_warnings_client.get_json", return_value=_load_fixture()):
            warnings = fetch_marine_warnings("PZZ545", session=MagicMock())
        # "Flood Watch" should be filtered out — only Small Craft Advisory + Special Marine
        events = [w["event"] for w in warnings]
        assert "Flood Watch" not in events
        assert "Small Craft Advisory" in events
        assert "Special Marine Warning" in events

    def test_sorted_severe_first(self):
        with patch("app.infra.noaa_warnings_client.get_json", return_value=_load_fixture()):
            warnings = fetch_marine_warnings("PZZ545", session=MagicMock())
        # "Special Marine Warning" is Severe, "Small Craft Advisory" is Moderate
        assert warnings[0]["severity"] == "Severe"
        assert warnings[1]["severity"] == "Moderate"

    def test_empty_zone_returns_empty_list(self):
        result = fetch_marine_warnings("", session=MagicMock())
        assert result == []

    def test_api_error_returns_empty_list(self):
        with patch("app.infra.noaa_warnings_client.get_json", side_effect=Exception("timeout")):
            result = fetch_marine_warnings("PZZ545", session=MagicMock())
        assert result == []

    def test_warning_dict_has_expected_keys(self):
        with patch("app.infra.noaa_warnings_client.get_json", return_value=_load_fixture()):
            warnings = fetch_marine_warnings("PZZ545", session=MagicMock())
        for w in warnings:
            for key in ("event", "headline", "severity", "urgency", "effective", "expires"):
                assert key in w, f"Missing key {key!r} in warning"
