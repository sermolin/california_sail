# Module Reference

This document catalogues every Python package and module in `app/`. For each module it states: what it does, which public symbols it exports, what it depends on, and any important caveats.

---

## Package map

```
app/
├── app.py                        Streamlit bootstrap
├── api/
│   └── main.py                   FastAPI ASGI app
├── bot/
│   ├── agent.py                  OpenRouter NL agent loop
│   ├── formatters.py             Telegram MarkdownV2 helpers
│   ├── slack.py                  Slack Bolt handler
│   ├── slack_formatters.py       Slack mrkdwn helpers
│   └── telegram.py               Telegram command handlers
├── domain/
│   ├── normalize.py              API JSON → Pandas DataFrame
│   ├── profiles.py               SailorProfile dataclass + YAML loader
│   ├── regions.py                SailingRegion / SailingZone + YAML loader
│   ├── scoring.py                Sailability algorithm
│   ├── units.py                  Unit conversion helpers
│   └── warnings.py               Synthetic warning generator (Sardinia)
├── infra/
│   ├── cache.py                  Generic in-memory TTL cache
│   ├── config.py                 Environment-based config dataclass
│   ├── forecast_cache.py         ForecastCache protocol + implementations
│   ├── http.py                   Shared requests session + get_json
│   ├── logging.py                Logging setup
│   ├── noaa_tides_client.py      NOAA CO-OPS tides API
│   ├── noaa_warnings_client.py   NOAA NWS GeoJSON warnings API
│   ├── open_meteo_client.py      Open-Meteo weather API
│   └── open_meteo_marine_client.py  Open-Meteo Marine API
├── mcp/
│   ├── serializers.py            ZoneForecast → JSON-safe dict
│   ├── server.py                 FastMCP server registration + entry point
│   └── tools.py                  8 MCP tool functions
├── services/
│   ├── forecast_service.py       Single-zone forecast orchestration
│   └── region_service.py         Multi-zone fan-out and ranking
├── ui/
│   ├── components.py             Reusable Streamlit widgets
│   ├── layout.py                 Top-level page layout
│   └── zone_filters.py           Pure zone filter helpers
└── viz/
    ├── charts.py                 Plotly chart builders
    └── themes.py                 Shared styling tokens
```

---

## `app/app.py`

**Role:** Streamlit application entry point.

Calls `app.ui.layout.run()` which renders the full single-page application. The only other responsibility is configuring the Streamlit page metadata (title, icon, layout).

---

## `app/api/main.py`

**Role:** FastAPI ASGI application that runs in the `california-sail-api` Cloud Run service.

| Symbol | Type | Description |
|---|---|---|
| `app` | `FastAPI` | The application instance |
| `_lifespan` | async context manager | On startup: registers Telegram webhook when `WEBHOOK_URL` env var is present; on shutdown: deregisters it |
| `health` | `GET /health` | Returns `{"status": "ok"}` — used as Cloud Run health check |
| `telegram_webhook` | `POST /telegram/webhook` | Accepts Telegram update JSON and dispatches to `python-telegram-bot` |
| `slack_events` | `POST /slack/events` | Accepts Slack event payloads and dispatches to Slack Bolt |
| MCP mount | `/mcp` | Mounts `mcp.sse_app()` for HTTP/SSE transport |

**Environment variables read:** `WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`.

---

## `app/bot/`

### `agent.py`

**Role:** Natural-language conversation agent backed by OpenRouter (any OpenAI-compatible model). Used by both the Telegram and Slack bots when a user sends a plain text message.

| Symbol | Description |
|---|---|
| `ConversationStore` | Thread-safe dict keyed by user ID; each value is a list of `{"role", "content"}` messages; evicts entries after `AGENT_TTL_MINUTES` |
| `TOOL_SCHEMAS` | JSON Schema definitions of all 8 MCP tools, passed to the model as `tools=` |
| `run_agent(user_id, message)` → `str` | Sends a message, calls tools in a loop until the model produces a plain text reply, returns the reply |
| `reset_history(user_id)` | Clears the conversation for `user_id` |
| `_dispatch(tool_name, args)` → `Any` | Calls the matching function in `app.mcp.tools` and returns the result |

**Environment variables read:** `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default: `anthropic/claude-3-haiku`), `AGENT_MAX_HISTORY`, `AGENT_TTL_MINUTES`.

---

### `formatters.py`

**Role:** Converts the JSON-safe dicts returned by `app.mcp.tools` into Telegram MarkdownV2 strings for display.

| Symbol | Description |
|---|---|
| `_esc(text)` | Escapes all MarkdownV2 reserved characters |
| `_bold(text)` | Wraps text in `*...*` |
| `format_regions(data)` | Lists regions with zone counts |
| `format_zones(data)` | Lists zones within a region |
| `format_profiles(data)` | Lists sailor profiles with key thresholds |
| `format_forecast(data)` | Full zone forecast: verdict, score, top metrics, best windows |
| `format_compare(data)` | Zone comparison table sorted by score |
| `format_windows(data)` | Top sailing windows with start time and score |
| `format_warnings(data)` | Active marine warnings |
| `format_explain(data)` | Per-component score breakdown for a specific hour |

> Note: All hyphens in zone IDs are escaped to `\-` per MarkdownV2 spec.

---

### `slack_formatters.py`

**Role:** Mirror of `formatters.py` for Slack mrkdwn syntax. Exposes the same `format_*` API but uses `*bold*`, backtick escaping, and Slack-flavoured link syntax.

---

### `telegram.py`

**Role:** Telegram bot command handlers plus the polling-mode entry point.

| Symbol | Description |
|---|---|
| `cmd_start` | `/start` — welcome message |
| `cmd_help` | `/help` — command list |
| `cmd_regions` | `/regions` — calls `mcp.tools.list_regions()` |
| `cmd_zones` | `/zones <region_id>` — calls `mcp.tools.list_zones()` |
| `cmd_profiles` | `/profiles` — calls `mcp.tools.list_profiles()` |
| `cmd_forecast` | `/forecast <zone_id> [profile_id] [days]` — calls `mcp.tools.get_zone_forecast()` |
| `cmd_compare` | `/compare <region_id> [profile_id]` — calls `mcp.tools.compare_zones_in_region()` |
| `cmd_windows` | `/windows <zone_id> [profile_id]` — calls `mcp.tools.best_sail_windows()` |
| `cmd_warnings` | `/warnings <region_id>` — calls `mcp.tools.get_active_warnings()` |
| `cmd_explain` | `/explain <zone_id> <hour_index>` — calls `mcp.tools.explain_score()` |
| `msg_fallback` | Plain text messages → `agent.run_agent()` (NL mode) |
| `build_application(token)` | Returns a configured `telegram.ext.Application` |
| `__main__` | Starts `application.run_polling()` for local development |

**Environment variables read:** `TELEGRAM_BOT_TOKEN` (required).

---

### `slack.py`

**Role:** Slack Bolt event handler. Handles `/sail-*` slash commands and `app_mention` events.

| Symbol | Description |
|---|---|
| `build_slack_handler()` | Returns a configured `SlackRequestHandler` |
| `_register_handlers(app)` | Registers all slash command and event listeners on a `Bolt App` |
| `_run_nl_agent(body, say, context)` | Called for `app_mention` — forwards text to `agent.run_agent()` |
| `_slack_uid(body)` | Hashes `team_id:user_id` for `ConversationStore` isolation |

**Environment variables read:** `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`.

---

## `app/domain/`

### `regions.py`

**Role:** Data models and YAML loader for regions and zones.

| Symbol | Type | Description |
|---|---|---|
| `SailingZone` | `@dataclass` | A sub-area within a region: `id`, `name`, `latitude`, `longitude`, `exposure` (`sheltered`/`open`/`channel`), `hazards: list[str]`, `flood_dir_deg: float \| None`, `tide_station_id: str \| None`, `nws_zone: str \| None` |
| `SailingRegion` | `@dataclass` | A named region: `id`, `name`, `country`, `timezone`, `zones: list[SailingZone]` |
| `load_regions(path)` | function | Parses `data/sailing_areas.yaml` and returns `list[SailingRegion]` |

---

### `profiles.py`

**Role:** Sailor profile model and YAML loader.

| Symbol | Type | Description |
|---|---|---|
| `SailorProfile` | `@dataclass` | Scoring thresholds: `id`, `name`, `wind_ideal_min_kt`, `wind_ideal_max_kt`, `gust_max_kt`, `wave_max_m`, `vis_min_km`, `low_chop_preference`, `chop_penalty_threshold_kt`, `chop_penalty_wave_period_s`, `wat_min_current_kt` |
| `load_profiles(path)` | function | Parses `data/sailor_profiles.yaml` |
| `get_profile_by_id(id)` | function | Returns a single profile or raises `KeyError` |
| `get_all_profiles()` | function | Returns all profiles as a list |
| `get_default_profile()` | function | Returns the `cruiser` profile |

---

### `normalize.py`

**Role:** Converts raw API JSON responses into Pandas DataFrames and merges them into a single hourly DataFrame.

| Symbol | Description |
|---|---|
| `open_meteo_response_to_df(raw)` | Validates keys and returns a DataFrame indexed by `time` (UTC) |
| `marine_response_to_df(raw)` | Same for Open-Meteo Marine; fills missing data with NaN |
| `noaa_tides_to_df(raw)` | Parses NOAA CO-OPS JSON predictions into a `time`/`tide_m` DataFrame |
| `merge_to_hourly(weather_df, marine_df, tides_df)` | Left-joins on the weather index; forward-fills tidal data; returns combined hourly DataFrame |

---

### `scoring.py`

**Role:** Computes the sailability score for each hourly row and derives summary statistics.

| Symbol | Description |
|---|---|
| `add_sailability_to_hourly(df, profile)` | Adds `score` (0–100) and `verdict` (`GO`/`MAYBE`/`NO-GO`) columns to the hourly DataFrame |
| `best_windows(df, window_hours, top_n)` | Finds the top N contiguous time windows with highest average score |
| `daily_sailability_avg(df)` | Groups by calendar day and returns mean score per day |
| `verdict(score)` | Returns the string verdict for a numeric score |

Score components (see [Domain Model](domain-model.md) for full algorithm):
1. Wind score (proximity to ideal range)
2. Gust penalty
3. Wave score (height + period)
4. Visibility penalty
5. Wind-against-tide (WAT) penalty

---

### `units.py`

**Role:** Pure conversion functions and geometric helpers.

| Symbol | Description |
|---|---|
| `ms_to_knots(v)` | m/s → knots |
| `knots_to_ms(v)` | knots → m/s |
| `m_to_ft(v)` | metres → feet |
| `c_to_f(v)` | Celsius → Fahrenheit |
| `deg_to_compass(deg)` | Degrees → cardinal string (N, NE, …) |
| `directions_opposed(dir_a, dir_b, threshold_deg)` | Returns `True` when the two headings are within `threshold_deg` of being opposite (used for WAT detection) |

---

### `warnings.py`

**Role:** Synthetic warning generator for regions that lack NOAA NWS coverage (currently Sardinia).

| Symbol | Description |
|---|---|
| `synthesize_warnings(df, zone_name)` | Inspects the next-24-hour slice of the hourly DataFrame for wind speed, wave height, and visibility thresholds; returns a list of warning dicts in the same schema as NOAA warnings |

---

## `app/infra/`

### `config.py`

**Role:** Loads runtime configuration from environment variables into a typed dataclass.

| Symbol | Description |
|---|---|
| `Config` | Dataclass with fields: `cache_ttl_seconds`, `forecast_days`, `http_timeout`, `http_retries`, `timezone_default` |
| `load_config()` | Reads `.env` via `python-dotenv` and environment, returns a `Config` instance |

---

### `http.py`

**Role:** Shared `requests.Session` with retry logic and a simple `get_json` wrapper.

| Symbol | Description |
|---|---|
| `create_session(retries, backoff)` | Returns a `requests.Session` with a `HTTPAdapter` attached |
| `get_json(url, params, headers, timeout)` → `dict` | GETs a URL and returns the parsed JSON body; raises `ApiUnavailableError` on HTTP errors or timeouts |
| `ApiUnavailableError` | Exception raised on non-2xx or connection errors |

---

### `forecast_cache.py`

**Role:** Decouples the caching strategy from the service layer so the same `get_zone_forecast` function works in both Streamlit (which owns its own cache) and background services (which need a process-local TTL cache).

| Symbol | Description |
|---|---|
| `ForecastCache` | Protocol with one method: `get_or_compute(key, ttl, compute) → Any` |
| `StreamlitForecastCache` | Sentinel implementation — `get_or_compute` simply calls `compute()`. Used to signal "let Streamlit's cache handle it" |
| `TTLForecastCache` | Thread-safe implementation backed by `cachetools.TTLCache` with a `threading.Lock` |
| `make_forecast_cache(backend)` | Factory; `backend="streamlit"` → `StreamlitForecastCache`, `backend="ttl"` → `TTLForecastCache` |

---

### `cache.py`

**Role:** Generic in-memory key/value TTL cache used outside of the forecast path (e.g. session state caching).

---

### `open_meteo_client.py`

**Role:** Fetches hourly weather forecasts from `api.open-meteo.com/v1/forecast`.

| Symbol | Description |
|---|---|
| `fetch_forecast(lat, lon, days, timeout)` → `dict` | Returns raw JSON response; raises `InvalidApiResponseError` if required hourly variables are missing |
| `InvalidApiResponseError` | Raised when the response schema is unexpected |

Variables requested: `wind_speed_10m`, `wind_direction_10m`, `wind_gusts_10m`, `temperature_2m`, `precipitation`, `cloud_cover`, `visibility`.

---

### `open_meteo_marine_client.py`

**Role:** Fetches wave forecast from `marine-api.open-meteo.com/v1/marine`.

| Symbol | Description |
|---|---|
| `fetch_marine_forecast(lat, lon, days, timeout)` → `dict` | Returns raw JSON; variables: `wave_height`, `wave_period`, `wave_direction` |

---

### `noaa_tides_client.py`

**Role:** Fetches tidal height predictions from NOAA CO-OPS API.

| Symbol | Description |
|---|---|
| `fetch_tide_predictions(station_id, days, datum, interval)` → `dict` | Returns CO-OPS JSON with `predictions` array; `datum="MLLW"`, `interval="h"` by default |

Only applicable to US zones with a `tide_station_id` set in `sailing_areas.yaml`.

---

### `noaa_warnings_client.py`

**Role:** Fetches active marine weather alerts from NOAA NWS `api.weather.gov/alerts/active`.

| Symbol | Description |
|---|---|
| `fetch_marine_warnings(nws_zone)` → `list[dict]` | Filters GeoJSON features by `zone` parameter; returns a list of alert dicts with `event`, `headline`, `description`, `effective`, `expires` |

Only applicable to US zones with an `nws_zone` set in `sailing_areas.yaml`.

---

### `logging.py`

**Role:** Centralised logging configuration.

| Symbol | Description |
|---|---|
| `setup_logging(level)` | Configures root logger with a standard format |
| `get_logger(name)` | Returns a named logger |

---

## `app/mcp/`

### `tools.py`

**Role:** Eight pure, testable functions that constitute the MCP tool surface. Each function: validates inputs, calls into the service layer, serialises the result via `serializers.py`, and returns a JSON-safe dict.

A module-level `TTLForecastCache` instance (15-minute TTL) is shared across all tool calls in the process.

| Tool function | Parameters | Returns |
|---|---|---|
| `list_regions()` | — | `list[dict]` with `id`, `name`, `country`, `zone_count` |
| `list_zones(region_id)` | region_id | `list[dict]` with zone metadata |
| `list_profiles()` | — | `list[dict]` with profile thresholds |
| `get_zone_forecast(zone_id, profile_id, days, summary)` | zone_id required; others optional | Full or summary `ZoneForecast` dict |
| `compare_zones_in_region(region_id, profile_id, days)` | region_id required | `list[dict]` sorted by score descending |
| `best_sail_windows(zone_id, profile_id, days, window_hours, top_n)` | zone_id required | `list[dict]` with `start`, `end`, `avg_score` |
| `get_active_warnings(region_id)` | region_id | `list[dict]` warnings |
| `explain_score(zone_id, hour_index, profile_id)` | zone_id, hour_index | `dict` with per-component score breakdown |

---

### `serializers.py`

**Role:** Converts Python domain objects and Pandas DataFrames into JSON-serialisable dicts, handling `numpy` float types, `NaT`, `None`, and optional hourly-row capping.

| Symbol | Description |
|---|---|
| `zone_forecast_to_dict(result, summary, hourly_cap)` | Main serialiser; `summary=True` omits raw hourly rows; `hourly_cap=48` limits rows |
| `zone_to_dict(zone)` | `SailingZone` → dict |
| `region_to_dict(region)` | `SailingRegion` → dict |
| `profile_to_dict(profile)` | `SailorProfile` → dict |
| `_safe_float(v)` | Returns Python `float` or `None` for numpy scalars |
| `_ts_iso(ts)` | Converts pandas Timestamp → ISO-8601 string |

---

### `server.py`

**Role:** Registers all tool functions with `FastMCP` and provides a CLI entry point to start the server in either `stdio` or `sse` transport mode.

```
python -m app.mcp.server               # stdio (for Cursor / Claude Desktop)
python -m app.mcp.server --transport sse --port 8765   # HTTP/SSE
```

The `mcp` instance is also imported by `app/api/main.py` and mounted at `/mcp` for the deployed SSE endpoint.

---

## `app/services/`

### `forecast_service.py`

**Role:** Orchestrates all API calls for a single zone and returns a `ZoneForecast`.

| Symbol | Type | Description |
|---|---|---|
| `ZoneForecast` | `@dataclass` | `zone: SailingZone`, `profile: SailorProfile`, `hourly: pd.DataFrame`, `warnings: list[dict]`, `fetched_at: datetime` |
| `_fetch_and_score(zone, profile, days)` | function | Core logic: parallel HTTP calls → normalise → merge → score → return ZoneForecast |
| `_st_get_zone_forecast(...)` | function | `@st.cache_data` decorated wrapper around `_fetch_and_score` (called only by Streamlit) |
| `get_zone_forecast(zone, profile, days, cache)` | function | Public entry point; dispatches to `_st_get_zone_forecast` or `cache.get_or_compute()` depending on the `cache` argument |

**Parallelism:** `concurrent.futures.ThreadPoolExecutor` is used inside `_fetch_and_score` to fire all four API calls simultaneously.

---

### `region_service.py`

**Role:** Fetches forecasts for all zones in a region (or a subset) and returns them ranked by sailability.

| Symbol | Description |
|---|---|
| `get_all_zone_forecasts(region, profile, days, cache)` | Calls `get_zone_forecast` for every zone in the region concurrently; returns a list sorted by descending average sailability score |
| `list_regions()` | Returns `load_regions()` result |
| `get_region_by_name(name)` | Case-insensitive region lookup by name or ID |

---

## `app/ui/`

### `layout.py`

**Role:** Top-level page orchestration for the Streamlit UI.

| Symbol | Description |
|---|---|
| `render_sidebar(regions, profiles)` | Renders sidebar controls: region selector, profile selector, days slider, zone multi-select |
| `render_zone_comparison(forecasts)` | Renders the overview tab: zone score cards and zone map |
| `render_zone_detail(forecast)` | Renders detail tabs for one zone: go/no-go header, summary metrics, charts (wind, waves, tides, etc.), warnings panel, sail windows |
| `run()` | Main entry point called from `app.py`; wires together sidebar state and the two render functions |

---

### `components.py`

**Role:** Reusable Streamlit widget functions (no layout logic).

| Symbol | Description |
|---|---|
| `go_nogo_header(verdict, score)` | Large coloured banner with verdict and score |
| `summary_metrics(forecast)` | Row of `st.metric` cards for key stats |
| `sailor_profile_selector(profiles)` | Dropdown returning selected `SailorProfile` |
| `warnings_panel(warnings)` | Expandable warning list with severity colouring |
| `sail_windows_section(windows)` | Top N windows as metric cards |
| `hazards_section(zone)` | Zone hazard tags |
| `scoring_formula_expander(forecast, profile)` | Expandable "how is the score computed?" explanation |
| `error_message(msg)` | Standardised error callout |
| `last_updated_at(fetched_at)` | Timestamp note |

---

### `zone_filters.py`

**Role:** Pure functions (no Streamlit dependency) for filtering and sorting `ZoneForecast` lists.

| Symbol | Description |
|---|---|
| `filter_forecasts(forecasts, zone_ids)` | Returns only forecasts whose zone ID is in `zone_ids` |
| `apply_top_n(forecasts, n)` | Returns top N by average score |
| `default_zone_index(forecasts, zone_id)` | Returns the list index of a given zone ID (for `st.selectbox` default) |

---

## `app/viz/`

### `charts.py`

**Role:** One function per chart type; each accepts a DataFrame (or other data) and returns a `plotly.graph_objects.Figure`.

| Symbol | Input | Output |
|---|---|---|
| `sailability_ribbon(df)` | hourly df | Coloured ribbon chart of score over time |
| `wind_rose(df)` | hourly df | Polar wind rose (speed × direction) |
| `wind_timeline_with_gusts(df)` | hourly df | Line chart: wind speed + gust range |
| `temperature_line(df)` | hourly df | Temperature time series |
| `cloud_precip_chart(df)` | hourly df | Dual-axis: cloud cover bar + precip line |
| `wave_height_period_bar(df)` | hourly df | Bar chart: wave height, overlaid wave period |
| `tide_curve(df)` | hourly df | Tide height over time |
| `wind_against_tide_timeline(df, zone)` | hourly df, zone | Highlights hours where wind opposes tide current |
| `zone_map(forecasts)` | list of ZoneForecast | Mapbox scatter map of zones coloured by verdict |

---

### `themes.py`

**Role:** Shared Plotly layout defaults and colour constants.

| Symbol | Description |
|---|---|
| `LAYOUT_DEFAULTS` | `dict` — common Plotly `layout` kwargs (font, margins, paper_bgcolor, etc.) |
| `SAILABILITY_COLORSCALE` | List of `[threshold, colour]` pairs for score colouring |
| `VERDICT_COLORS` | `{"GO": ..., "MAYBE": ..., "NO-GO": ...}` |
| `VERDICT_EMOJI` | `{"GO": "✅", "MAYBE": "⚠️", "NO-GO": "❌"}` |
