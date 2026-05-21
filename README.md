# ⛵ California Sail — Forecast

A Streamlit application that helps sailors decide **where to go and when to sail** across three iconic regions: **San Francisco Bay**, **Puget Sound (Seattle)**, and **Sardinia**.

It fetches live weather, wave, and tidal data, scores every zone on a 0–100 **Sailability** scale, and gives you a clear **GO / MAYBE / NO-GO** verdict tailored to your sailor profile.

---

## Live data sources

| Source | Data |
|---|---|
| [Open-Meteo Weather](https://open-meteo.com/) | Wind speed/gusts/direction, temperature, precipitation, cloud cover, visibility |
| [Open-Meteo Marine](https://marine-api.open-meteo.com/) | Wave height, wave period, wave direction, swell height, sea level |
| [NOAA CO-OPS Tides](https://tidesandcurrents.noaa.gov/) | Hourly water-level predictions (US regions only) |
| [NOAA NWS Alerts](https://www.weather.gov/) | Active marine warnings — Small Craft Advisory, Gale Warning, etc. (US only) |

All external calls use retry logic, timeouts, and Streamlit's `@st.cache_data` to minimise API load.

---

## Sailor profiles

Choose your profile in the sidebar — it adjusts **all** scoring thresholds:

| Profile | Ideal wind | Gust gate | Wave gate | Vis gate | Chop sensitivity |
|---|---|---|---|---|---|
| 🎓 School / Beginner | 5–12 kt | 20 kt | 1.0 m | 3.0 km | High |
| ⛵ Cruiser *(default)* | 10–18 kt | 30 kt | 2.5 m | 1.0 km | Medium |
| 🏆 Racer | 14–25 kt | 35 kt | 3.5 m | 1.0 km | Low |

---

## Sailability scoring formula (v3)

```
Sailability (0–100) = weighted blend of component scores, minus WAT penalty
                      (capped at 25 if any hard gate fails)

1. Hard safety gates — any failure → score ≤ 25
     gust_kt       > profile.max_gust_kt
     visibility_m  < profile.min_visibility_m
     wave_height_m > profile.max_wave_m  (when wave data available)

2. Component scores (0–100 each)
     wind_score       Gaussian peak at profile.ideal_wind_mid (σ = 8 kt)
     sea_score        Linear decay with wave height; −chop_penalty when period short
     visibility_score Linear: 100 at 10 km → 0 at min_visibility_m

3. Weighted blend
     With wave data:  0.40 × wind + 0.35 × sea + 0.25 × visibility
     Without:         0.55 × wind + 0.45 × visibility

4. Wind-against-tide penalty (0–25 pts)
     Active when current speed > profile.wat_min_current_kt AND
     wind direction opposes tidal current direction.
     Magnitude proportional to current speed (max at 3 kt).

Verdict: GO ≥ 65 · MAYBE 35–64 · NO-GO < 35
```

---

## Running locally

### Prerequisites

- Python 3.9+
- [pip](https://pip.pypa.io/)

### Setup

```bash
git clone https://github.com/lissianski/california_sail.git
cd california_sail
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
streamlit run app/app.py
```

Open **http://localhost:8501** in your browser.

> **Note:** Run from your own terminal (not from inside Cursor's sandboxed shell) so that external API calls are not blocked by the IDE's proxy.

### Configuration

Copy `.env.example` to `.env` and adjust if needed:

```bash
cp .env.example .env
```

Key settings:

| Variable | Default | Description |
|---|---|---|
| `CACHE_TTL_SECONDS` | `900` | How long (s) to cache API responses |
| `HTTP_TIMEOUT_SECONDS` | `8` | Per-request timeout |
| `HTTP_RETRIES` | `3` | Retry attempts on 5xx errors |

---

## Project structure

```
california_sail/
├── app/
│   ├── app.py                      # Streamlit entry point
│   ├── domain/
│   │   ├── profiles.py             # SailorProfile dataclass + YAML loader
│   │   ├── regions.py              # SailingRegion / SailingZone + YAML loader
│   │   ├── scoring.py              # Sailability v3 (vectorized, profile-driven)
│   │   ├── normalize.py            # API response → canonical DataFrames
│   │   └── units.py                # Unit conversion helpers
│   ├── infra/
│   │   ├── http.py                 # Session with retries + error handling
│   │   ├── config.py               # Settings from env vars
│   │   ├── cache.py                # TTL in-memory cache
│   │   ├── open_meteo_client.py    # Weather API client
│   │   ├── open_meteo_marine_client.py  # Marine waves API client
│   │   ├── noaa_tides_client.py    # NOAA CO-OPS tides API client
│   │   └── noaa_warnings_client.py # NOAA NWS alerts API client
│   ├── services/
│   │   ├── forecast_service.py     # Per-zone orchestration (concurrent fetch → score)
│   │   └── region_service.py       # Per-region ranking of all zones
│   ├── ui/
│   │   ├── layout.py               # Full Streamlit page layout
│   │   └── components.py           # Reusable UI components
│   └── viz/
│       ├── charts.py               # Plotly chart builders (pure functions)
│       └── themes.py               # Shared layout defaults + colour scales
├── data/
│   ├── sailing_areas.yaml          # Region + zone definitions
│   └── sailor_profiles.yaml        # Scoring profile presets
├── tests/
│   ├── fixtures/                   # Recorded API responses for offline tests
│   └── test_*.py                   # Unit + contract tests
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Sailing regions & zones

### San Francisco Bay
| Zone | Lat/Lon | Exposure | Flood direction |
|---|---|---|---|
| City Front | 37.808 / -122.435 | Open | 55° (ENE) |
| Berkeley Olympic Circle | 37.866 / -122.318 | Open | 90° (E) |
| Raccoon Strait | 37.873 / -122.460 | Channel | 65° (ENE) |
| South Bay / Coyote Pt | 37.594 / -122.319 | Sheltered | 160° (SSE) |

### Puget Sound (Seattle)
| Zone | Lat/Lon | Exposure |
|---|---|---|
| Shilshole Bay | 47.688 / -122.407 | Open |
| Port Townsend | 48.113 / -122.759 | Open |
| Elliott Bay | 47.607 / -122.341 | Open |
| Possession Sound | 47.995 / -122.278 | Open |

### Sardinia
| Zone | Lat/Lon | Exposure |
|---|---|---|
| Costa Smeralda | 41.082 / 9.533 | Open |
| Bonifacio Strait | 41.370 / 9.150 | Channel |
| Cagliari Gulf | 39.182 / 9.122 | Open |
| Alghero | 40.570 / 8.316 | Open |

---

## Tests

```bash
pytest tests/ -q
```

171 tests covering domain logic, API client contracts, scoring v3 per-profile differences, and chart smoke tests. All tests run offline using recorded JSON fixtures — no live API calls.

---

## Docker

```bash
docker build -t california-sail .
docker run -p 8501:8501 california-sail
```

---

## Deployment — Streamlit Community Cloud

1. Fork / push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io/) → **New app**.
3. Select the repo, branch `main`, and entry point `app/app.py`.
4. Add any environment variables under **Advanced settings → Secrets**.
5. Click **Deploy** — done.

---

---

## Using as an MCP Server (Phase 4a)

California Sail exposes its forecast services as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server.  Any MCP-aware AI agent — Cursor, Claude Desktop, OpenAI Agents SDK, or a future Telegram/Slack bot — can call the 8 tools below to get live sailing conditions.

### Available tools

| Tool | Description |
|---|---|
| `list_regions` | List all regions (SF Bay, Puget Sound, Sardinia) |
| `list_zones` | List sailing zones within a region |
| `list_profiles` | List sailor profiles (school, cruiser, racer) |
| `get_zone_forecast` | Fetch scored forecast for a zone |
| `compare_zones_in_region` | Rank all zones in a region by sailability |
| `best_sail_windows` | Find the top 3 best sailing time windows |
| `get_active_warnings` | Get active NOAA marine warnings (US only) |
| `explain_score` | Explain the sailability score for a specific hour |

### Transport modes

**stdio** (for Cursor / Claude Desktop — the client starts the process):

```bash
python -m app.mcp.server          # defaults to stdio
```

**SSE** (HTTP + Server-Sent Events, for remote agents / bots):

```bash
python -m app.mcp.server --transport sse --port 8765
# agents connect to: http://127.0.0.1:8765/sse
```

### Cursor configuration

Add to your workspace `.cursor/mcp.json` (update paths to match your installation):

```json
{
  "mcpServers": {
    "california-sail": {
      "command": "/path/to/california_sail/.venv/bin/python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/california_sail"
    }
  }
}
```

A ready-to-paste snippet is at `examples/mcp/cursor.json`.

### Claude Desktop configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "california-sail": {
      "command": "/path/to/california_sail/.venv/bin/python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/california_sail"
    }
  }
}
```

A ready-to-paste snippet is at `examples/mcp/claude_desktop.json`.

### Sample agent prompts

Once connected, an agent can answer questions like:

1. **"Where should I sail in SF Bay this afternoon?"** — agent calls `compare_zones_in_region("sf-bay")` and optionally `get_active_warnings("sf-bay")`.
2. **"What's the best time to sail from Shilshole this weekend?"** — agent calls `best_sail_windows("shilshole", days=3)`.
3. **"Is it safe to take students out on the bay today?"** — agent calls `get_zone_forecast("city-front", profile_id="school")` and `get_active_warnings("sf-bay")`.
4. **"Why did Berkeley Olympic Circle score only 42?"** — agent calls `explain_score("berkeley-oc")` to get a plain-language breakdown.
5. **"Compare all Sardinia zones for a racing sailor."** — agent calls `compare_zones_in_region("sardinia", profile_id="racer")`.

### Notes

- The MCP server reads **no user state** — it is purely a forecast query service.
- Authentication on the SSE transport is not implemented (fine for localhost dev).
- The server uses a 15-minute in-process TTL cache (`TTLForecastCache`) so repeated calls in the same session hit live APIs at most once per quarter-hour.

---

## Out of scope (deferred)

- Paid tidal current data for Sardinia (Stormglass)
- User accounts / persistent preferences / push notifications
- Custom user-defined zones
- Race-route planning / polar performance diagrams
- Channel adapters (Telegram, Slack) — Phase 4b/4c
- Authentication on the MCP HTTP transport — Phase 5 (GCP)
