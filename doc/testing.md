# Testing

This document describes the test suite structure, how to run tests, what each module covers, and how fixtures work.

---

## Running the tests

```bash
# All tests
pytest

# Verbose output
pytest -v

# One module
pytest tests/test_scoring.py -v

# With coverage report
pytest --cov=app --cov-report=term-missing

# Only fast unit tests (exclude integration-ish tests)
pytest -k "not forecast_service and not region_service" -v
```

`pyproject.toml` configures pytest:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]   # so "import app" works without pip install -e .
```

---

## Test suite layout

```
tests/
├── conftest.py                     # Shared fixtures
├── fixtures/                       # Static API response mocks
│   ├── open_meteo_response.json    # Open-Meteo weather response
│   ├── open_meteo_marine_response.json
│   ├── noaa_tides_response.json    # NOAA CO-OPS tides response
│   ├── noaa_warnings_response.json # NOAA NWS GeoJSON alerts
│   └── sailing_areas.yaml          # Minimal YAML for region/zone tests
└── test_*.py (22 modules)
```

---

## `conftest.py` — shared fixtures

| Fixture | Scope | Description |
|---|---|---|
| `fixtures_dir` | session | `pathlib.Path` to `tests/fixtures/` |
| `open_meteo_fixture` | function | Parsed dict from `open_meteo_response.json` |
| `sailing_areas_yaml` | function | Path to `tests/fixtures/sailing_areas.yaml` |
| `env_reset` | autouse, function | Saves and restores `os.environ` so env-mutating tests don't bleed into each other |

---

## Test modules

### Infrastructure layer

| File | What it tests |
|---|---|
| `test_config.py` | `Config` defaults; env var overrides; `load_config()` returns correct types |
| `test_forecast_cache.py` | `StreamlitForecastCache`: always calls `compute`; `TTLForecastCache`: cache hit/miss/expiry; thread safety with 10 concurrent threads; `make_forecast_cache` factory |

### Domain layer

| File | What it tests |
|---|---|
| `test_regions.py` | YAML parsing; `SailingZone` and `SailingRegion` field types; duplicate zone ID detection |
| `test_profiles.py` | Profile YAML load; `get_profile_by_id` happy path and missing ID; `get_default_profile` returns `cruiser`; threshold ordering (school < cruiser < racer for max wind) |
| `test_units.py` | `ms_to_knots`, `knots_to_ms`, `m_to_ft`, `c_to_f`, `deg_to_compass`; `directions_opposed` for aligned, opposed, and edge-case headings |
| `test_normalize.py` | `open_meteo_response_to_df`: column names, dtypes, index; `marine_response_to_df`: wave columns; `noaa_tides_to_df`: tide column; `merge_to_hourly`: correct join, NaN fill |
| `test_scoring.py` | Score = 0–100 bounds; ideal-wind zone gets high score; wind below min gets partial score; gust hard gate; wave hard gate; visibility hard gate; WAT penalty applied when current opposes wind; `best_windows` returns sorted non-overlapping windows; `verdict` thresholds; profile differences (school vs racer same data) |
| `test_warnings_synthesizer.py` | `synthesize_warnings`: wind > threshold → warning; wave > threshold → warning; fog → warning; 24-hour window only; output schema matches NOAA format |

### Infrastructure clients

| File | What it tests |
|---|---|
| `test_open_meteo_client.py` | `fetch_forecast` with mocked `get_json`; validates required hourly fields; raises `InvalidApiResponseError` on missing keys |
| `test_open_meteo_marine_client.py` | Same pattern for marine client |
| `test_noaa_tides_client.py` | `fetch_tide_predictions` with mocked response; correct station ID and parameters passed |
| `test_noaa_warnings_client.py` | GeoJSON parsing; zone filtering; missing zone returns empty list |

### Service layer

| File | What it tests |
|---|---|
| `test_forecast_service.py` | `_fetch_and_score` integration: all four API clients mocked; verifies `ZoneForecast` shape, hourly DataFrame columns, warnings list; Sardinia (no NOAA) synthesises warnings |
| `test_region_service.py` | `get_all_zone_forecasts`: concurrent calls, sorted by score descending; `get_region_by_name`: exact match, case-insensitive, not found |

### MCP layer

| File | What it tests |
|---|---|
| `test_mcp_serializers.py` | `zone_forecast_to_dict`: JSON-safe (no numpy, no NaT); `summary=True` omits hourly; `hourly_cap=5` limits rows; `_safe_float` handles numpy float32/64 and None; `_ts_iso` returns ISO string |
| `test_mcp_tools.py` | All 8 tools with mocked service layer; verifies return shape (dict keys present); error cases (unknown zone/region ID); `explain_score` component keys; `compare_zones_in_region` sorted |

### UI / Viz layer

| File | What it tests |
|---|---|
| `test_charts.py` | Every chart builder with both empty and populated DataFrames; verifies `Figure` type returned; no exceptions on NaN-heavy data |
| `test_zone_filters.py` | `filter_forecasts` with known/unknown zone IDs; `apply_top_n` truncates correctly; `default_zone_index` returns correct index |

### Bot layer

| File | What it tests |
|---|---|
| `test_bot_formatters.py` | `format_regions`, `format_zones`, `format_profiles`, `format_forecast`, `format_compare`, `format_windows`, `format_warnings`, `format_explain` — smoke tests: non-empty string, key tokens present (with MarkdownV2 escaping awareness) |
| `test_slack_formatters.py` | Same as above for Slack mrkdwn formatters |
| `test_bot_agent.py` | `ConversationStore`: add/get/evict; `run_agent`: no-tools path; tool-calling loop with mock OpenRouter; `reset_history` clears state; unknown tool in `_dispatch` returns error string |
| `test_slack_bot.py` | `build_slack_handler`: requires `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET`; raises without env vars; `_slack_uid` produces deterministic hash |

---

## Fixtures — API response mocks

The JSON files in `tests/fixtures/` are real API response shapes with real-ish values.

### `open_meteo_response.json`

```json
{
  "hourly": {
    "time": ["2026-05-14T00:00", ...],
    "wind_speed_10m": [8.2, ...],
    "wind_direction_10m": [290, ...],
    "wind_gusts_10m": [13.4, ...],
    "temperature_2m": [14.1, ...],
    "precipitation": [0.0, ...],
    "cloud_cover": [20, ...],
    "visibility": [24140, ...]
  }
}
```

### `open_meteo_marine_response.json`

```json
{
  "hourly": {
    "time": [...],
    "wave_height": [0.8, ...],
    "wave_period": [8.2, ...],
    "wave_direction": [310, ...]
  }
}
```

### `noaa_tides_response.json`

```json
{
  "predictions": [
    {"t": "2026-05-14 00:00", "v": "1.234"},
    ...
  ]
}
```

### `noaa_warnings_response.json`

```json
{
  "features": [
    {
      "properties": {
        "event": "Small Craft Advisory",
        "headline": "...",
        "description": "...",
        "effective": "2026-05-14T12:00:00-07:00",
        "expires": "2026-05-14T21:00:00-07:00",
        "severity": "Moderate"
      }
    }
  ]
}
```

### `tests/fixtures/sailing_areas.yaml`

A minimal version with one region and two zones, used to keep region/zone tests fast and independent of the real data file.

---

## Mocking strategy

All HTTP calls are mocked using `unittest.mock.patch`. The general pattern:

```python
from unittest.mock import patch

def test_fetch_forecast(open_meteo_fixture):
    with patch("app.infra.open_meteo_client.get_json", return_value=open_meteo_fixture):
        result = fetch_forecast(lat=37.8, lon=-122.4, days=3)
    assert "hourly" in result
```

For the MCP tool tests, the service layer is patched at the import site in `app.mcp.tools`:

```python
with patch("app.mcp.tools._svc_get_zone_forecast", return_value=fake_zone_forecast):
    result = get_zone_forecast("city-front")
assert result["verdict"] in ("GO", "MAYBE", "NO-GO")
```

---

## What is not covered

| Area | Reason |
|---|---|
| Streamlit UI rendering | Streamlit's test utilities are not used; UI is manually tested |
| End-to-end bot integration | Would require a live Telegram token; tested manually |
| Cloud Run deployment | Tested via `./scripts/deploy.sh` and manual verification |
| OpenRouter model responses | Agent tests mock the OpenAI client; model quality is not tested |
