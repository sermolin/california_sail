"""Tests for NOAA CO-OPS tides client (contract + validation)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.infra.noaa_tides_client import (
    InvalidNoaaTidesResponseError,
    _validate_tides_response,
    fetch_tide_predictions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_tides_fixture() -> dict:
    return json.loads((FIXTURES / "noaa_tides_response.json").read_text())


class TestValidateTidesResponse:
    def test_valid_response_passes(self):
        _validate_tides_response(_load_tides_fixture())

    def test_missing_predictions_raises(self):
        with pytest.raises(InvalidNoaaTidesResponseError, match="predictions"):
            _validate_tides_response({})

    def test_empty_predictions_raises(self):
        with pytest.raises(InvalidNoaaTidesResponseError, match="empty"):
            _validate_tides_response({"predictions": []})

    def test_error_message_included(self):
        raw = {"error": {"message": "Unknown station"}}
        with pytest.raises(InvalidNoaaTidesResponseError, match="Unknown station"):
            _validate_tides_response(raw)


class TestFetchTidePredictions:
    def test_returns_dict_with_predictions(self):
        mock_session = MagicMock()
        with patch("app.infra.noaa_tides_client.get_json", return_value=_load_tides_fixture()):
            result = fetch_tide_predictions("9414290", days=3, session=mock_session)
        assert "predictions" in result
        assert len(result["predictions"]) == 13

    def test_date_range_parameters_sent(self):
        captured = {}
        def fake_get_json(session, url, params):
            captured["params"] = params
            return _load_tides_fixture()
        mock_session = MagicMock()
        ref = date(2026, 5, 15)
        with patch("app.infra.noaa_tides_client.get_json", side_effect=fake_get_json):
            fetch_tide_predictions("9414290", days=3, session=mock_session, reference_date=ref)
        assert captured["params"]["begin_date"] == "20260515"
        assert captured["params"]["end_date"] == "20260518"
        assert captured["params"]["product"] == "predictions"
        assert captured["params"]["interval"] == "h"
        assert captured["params"]["units"] == "metric"
