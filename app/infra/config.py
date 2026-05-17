"""Application configuration: defaults + environment overrides."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """California Sail application configuration."""

    timezone_default: str = "America/Los_Angeles"
    forecast_days: int = 7
    http_timeout_seconds: int = 8
    http_retries: int = 2
    cache_ttl_seconds: int = 900
    cache_backend: str = "memory"

    @classmethod
    def load(cls, env: dict[str, str] | None = None) -> "Config":
        """Build config from defaults then override from env (or provided dict)."""
        source = env if env is not None else os.environ

        def str_or(key: str, default: str) -> str:
            return source.get(key, default).strip() or default

        def int_or(key: str, default: int) -> int:
            raw = source.get(key, str(default)).strip()
            try:
                return int(raw) if raw else default
            except ValueError:
                return default

        return cls(
            timezone_default=str_or("TIMEZONE_DEFAULT", "America/Los_Angeles"),
            forecast_days=max(1, min(16, int_or("FORECAST_DAYS", 7))),
            http_timeout_seconds=max(1, int_or("HTTP_TIMEOUT_SECONDS", 8)),
            http_retries=max(0, int_or("HTTP_RETRIES", 2)),
            cache_ttl_seconds=max(0, int_or("CACHE_TTL_SECONDS", 900)),
            cache_backend=str_or("CACHE_BACKEND", "memory"),
        )


def load_config(env: dict[str, str] | None = None) -> Config:
    """Load application configuration."""
    return Config.load(env=env)
