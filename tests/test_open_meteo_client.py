"""Contract tests for infra/open_meteo_client.py using recorded fixture."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.infra.open_meteo_client import (
    InvalidApiResponseError,
    _validate_response,
    fetch_forecast,
)


class TestValidateResponse:
    def test_valid_response_passes(self, open_meteo_fixture):
        _validate_response(open_meteo_fixture)  # must not raise

    def test_missing_hourly_raises(self):
        with pytest.raises(InvalidApiResponseError, match="hourly"):
            _validate_response({})

    def test_missing_wind_speed_raises(self):
        raw = {"hourly": {"time": [], "temperature_2m": []}}
        with pytest.raises(InvalidApiResponseError, match="missing fields"):
            _validate_response(raw)

    def test_missing_temperature_raises(self):
        raw = {"hourly": {"time": [], "wind_speed_10m": []}}
        with pytest.raises(InvalidApiResponseError, match="missing fields"):
            _validate_response(raw)


class TestFetchForecast:
    def test_returns_dict_from_fixture(self, open_meteo_fixture):
        mock_session = MagicMock()
        mock_session.get.return_value.ok = True
        mock_session.get.return_value.json.return_value = open_meteo_fixture

        result = fetch_forecast(37.808, -122.435, days=1, session=mock_session)
        assert isinstance(result, dict)
        assert "hourly" in result

    def test_request_params_include_required_fields(self, open_meteo_fixture):
        mock_session = MagicMock()
        mock_session.get.return_value.ok = True
        mock_session.get.return_value.json.return_value = open_meteo_fixture

        fetch_forecast(37.808, -122.435, days=3, timezone="America/Los_Angeles", session=mock_session)

        call_kwargs = mock_session.get.call_args
        params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
        assert "wind_speed_10m" in params.get("hourly", "")
        assert "wind_gusts_10m" in params.get("hourly", "")
        assert params["forecast_days"] == 3

    def test_days_clamped_to_16(self, open_meteo_fixture):
        mock_session = MagicMock()
        mock_session.get.return_value.ok = True
        mock_session.get.return_value.json.return_value = open_meteo_fixture

        fetch_forecast(37.0, -122.0, days=99, session=mock_session)
        call_kwargs = mock_session.get.call_args
        params = call_kwargs[1].get("params") or call_kwargs[0][1]
        assert params["forecast_days"] == 16
