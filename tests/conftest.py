"""Pytest configuration and shared fixtures for California Sail."""
import json
from pathlib import Path

import pytest


ENV_VARS = [
    "TIMEZONE_DEFAULT",
    "FORECAST_DAYS",
    "HTTP_TIMEOUT_SECONDS",
    "HTTP_RETRIES",
    "CACHE_TTL_SECONDS",
    "CACHE_BACKEND",
]


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Prevent environment variable leakage between tests."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def open_meteo_fixture(fixtures_dir) -> dict:
    return json.loads((fixtures_dir / "open_meteo_response.json").read_text())


@pytest.fixture
def sailing_areas_yaml(fixtures_dir) -> Path:
    return fixtures_dir / "sailing_areas.yaml"
