"""Tests for infra/config.py."""
import pytest
from app.infra.config import Config, load_config


class TestConfigDefaults:
    def test_default_values(self):
        cfg = Config.load(env={})
        assert cfg.forecast_days == 7
        assert cfg.timezone_default == "America/Los_Angeles"
        assert cfg.http_timeout_seconds == 8
        assert cfg.http_retries == 2
        assert cfg.cache_ttl_seconds == 900

    def test_env_overrides(self):
        cfg = Config.load(env={
            "FORECAST_DAYS": "5",
            "TIMEZONE_DEFAULT": "Europe/Rome",
            "CACHE_TTL_SECONDS": "300",
        })
        assert cfg.forecast_days == 5
        assert cfg.timezone_default == "Europe/Rome"
        assert cfg.cache_ttl_seconds == 300

    def test_forecast_days_clamped_max(self):
        cfg = Config.load(env={"FORECAST_DAYS": "99"})
        assert cfg.forecast_days == 16

    def test_forecast_days_clamped_min(self):
        cfg = Config.load(env={"FORECAST_DAYS": "0"})
        assert cfg.forecast_days == 1

    def test_invalid_int_falls_back_to_default(self):
        cfg = Config.load(env={"FORECAST_DAYS": "notanumber"})
        assert cfg.forecast_days == 7

    def test_load_config_convenience(self):
        cfg = load_config(env={})
        assert isinstance(cfg, Config)
