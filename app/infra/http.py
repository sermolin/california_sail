"""HTTP session with timeout, retries, and central error handling."""
from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.infra.config import load_config

USER_AGENT = "CaliforniaSailForecast/1.0"


class ApiUnavailableError(Exception):
    """Raised when an API is unreachable or returns a non-2xx status."""


def create_session(
    timeout_seconds: int | None = None,
    retries: int | None = None,
) -> requests.Session:
    """Create a requests Session with timeout, retries, and a fixed User-Agent."""
    config = load_config()
    timeout = timeout_seconds if timeout_seconds is not None else config.http_timeout_seconds
    retry_count = retries if retries is not None else config.http_retries

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.timeout = timeout  # type: ignore[attr-defined]

    retry_strategy = Retry(
        total=retry_count,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def get_json(session: requests.Session, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict:
    """GET url with optional params and headers, parse JSON. Raises ApiUnavailableError on failure."""
    try:
        resp = session.get(url, params=params, headers=headers, timeout=getattr(session, "timeout", 8))
    except requests.RequestException as e:
        raise ApiUnavailableError(f"Request failed for {url}: {e}") from e

    if not resp.ok:
        raise ApiUnavailableError(
            f"HTTP {resp.status_code} for {url}: {resp.text[:200]}"
        )

    try:
        return resp.json()
    except ValueError as e:
        raise ApiUnavailableError(f"Invalid JSON from {url}: {e}") from e
