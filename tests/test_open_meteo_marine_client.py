"""Tests for Open-Meteo Marine client (contract + validation)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.infra.open_meteo_marine_client import (
    InvalidMarineApiResponseError,
    _validate_marine_response,
    fetch_marine_forecast,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_marine_fixture() -> dict:
    return json.loads((FIXTURES / "open_meteo_marine_response.json").read_text())


class TestValidateMarineResponse:
    def test_valid_response_passes(self):
        _validate_marine_response(_load_marine_fixture())  # should not raise

    def test_missing_hourly_raises(self):
        with pytest.raises(InvalidMarineApiResponseError, match="hourly"):
            _validate_marine_response({})

    def test_missing_wave_height_raises(self):
        raw = _load_marine_fixture()
        del raw["hourly"]["wave_height"]
        with pytest.raises(InvalidMarineApiResponseError, match="wave_height"):
            _validate_marine_response(raw)

    def test_missing_time_raises(self):
        raw = _load_marine_fixture()
        del raw["hourly"]["time"]
        with pytest.raises(InvalidMarineApiResponseError, match="time"):
            _validate_marine_response(raw)


class TestFetchMarineForecast:
    def test_returns_dict_with_hourly(self):
        mock_session = MagicMock()
        with patch("app.infra.open_meteo_marine_client.get_json", return_value=_load_marine_fixture()):
            result = fetch_marine_forecast(37.808, -122.435, days=3, session=mock_session)
        assert "hourly" in result
        assert "wave_height" in result["hourly"]

    def test_forecast_days_clamped_to_16(self):
        captured = {}
        def fake_get_json(session, url, params):
            captured["params"] = params
            return _load_marine_fixture()
        mock_session = MagicMock()
        with patch("app.infra.open_meteo_marine_client.get_json", side_effect=fake_get_json):
            fetch_marine_forecast(37.808, -122.435, days=99, session=mock_session)
        assert captured["params"]["forecast_days"] == 16
