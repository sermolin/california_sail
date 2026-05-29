# California Sail — Developer Guide

California Sail is a sailing-conditions decision-support platform. It fetches real-time weather, waves, tides, and marine warnings for three sailing regions — **San Francisco Bay**, **Puget Sound (Seattle)**, and **Sardinia** — and synthesizes them into scored, profile-aware go/no-go recommendations. The same core data is exposed through four surfaces: a Streamlit web UI, an MCP server for AI agents, a Telegram bot, and a Slack bot.

---

## Contents

| Document | What it covers |
|---|---|
| [Architecture](architecture.md) | System layers, component map, deployment topology, data-flow diagrams |
| [Modules](modules.md) | Every Python package and module in `app/` — purpose, key symbols, relationships |
| [Domain Model](domain-model.md) | `SailingRegion`, `SailingZone`, `SailorProfile`, `ZoneForecast`, scoring algorithm |
| [Local Setup](local-setup.md) | Prerequisites, virtual environment, environment variables, run commands |
| [Deployment](deployment.md) | GCP Cloud Run, Artifact Registry, Cloud Build, Secret Manager, `deploy.sh` |
| [Integrations](integrations.md) | MCP server (stdio + SSE), Telegram bot, Slack bot, OpenRouter NL agent |
| [Testing](testing.md) | Test layout, fixtures, how to run, coverage targets |

---

## Technology stack

| Layer | Technology |
|---|---|
| Web UI | Streamlit + Plotly |
| API / webhooks | FastAPI + Uvicorn |
| MCP server | FastMCP (`mcp[cli]`) |
| Bot framework | python-telegram-bot, Slack Bolt |
| NL agent | OpenRouter (Claude Haiku by default) via OpenAI-compat SDK |
| Data | Pandas, NumPy |
| Weather APIs | Open-Meteo (weather), Open-Meteo Marine (waves), NOAA CO-OPS (tides), NOAA NWS (warnings) |
| Configuration | YAML files (`data/`) + `.env` / Secret Manager |
| Caching | `st.cache_data` (Streamlit), `TTLForecastCache` (MCP / bots) |
| Containerisation | Docker (two images: `Dockerfile.ui`, `Dockerfile.api`) |
| Cloud | Google Cloud Run + Artifact Registry + Secret Manager |
| Testing | pytest |

---

## Repository layout

```
california_sail/
├── app/                     # All application source code
│   ├── app.py               # Streamlit entry point
│   ├── api/                 # FastAPI ASGI app (webhooks + MCP SSE)
│   ├── bot/                 # Telegram bot, Slack bot, NL agent, formatters
│   ├── domain/              # Pure data models, normalisation, scoring, units
│   ├── infra/               # HTTP client, config, caching, external API clients
│   ├── mcp/                 # MCP server, tool functions, serialisers
│   ├── services/            # Forecast orchestration (ties domain + infra together)
│   ├── ui/                  # Streamlit layout and widget components
│   └── viz/                 # Plotly chart builders and theme
├── data/
│   ├── sailing_areas.yaml   # Region and zone definitions
│   └── sailor_profiles.yaml # Sailor scoring profiles
├── doc/                     # ← you are here
├── examples/mcp/            # Cursor / Claude Desktop MCP config snippets
├── scripts/
│   └── deploy.sh            # Cloud Run deploy script
├── tests/                   # pytest test suite (22 modules)
├── Dockerfile.ui            # Image for the Streamlit service
├── Dockerfile.api           # Image for the FastAPI/bot/MCP service
├── docker-compose.yml       # Local integration: ui + api side by side
├── cloudbuild.ui.yaml       # Cloud Build config for UI image
├── cloudbuild.api.yaml      # Cloud Build config for API image
├── pyproject.toml           # Package metadata, ruff, pytest config
├── requirements.txt         # Runtime + dev dependencies
├── .env.example             # Template for local environment variables
└── run.sh                   # Convenience script: source .venv + streamlit run
```

---

## Quick start (60 seconds)

```bash
# 1. Clone and set up
git clone <repo-url> california_sail && cd california_sail
./setup.sh          # creates .venv, pip install, copies .env.example → .env

# 2. (Optional) Configure environment
cp .env.example .env   # already done by setup.sh; edit as needed

# 3. Run the Streamlit UI
./run.sh            # opens http://localhost:8501

# 4. Run the full stack locally (UI + API + bot)
docker compose up   # UI on :8501, API on :8080
```

See [Local Setup](local-setup.md) for full details.

---

## Key concepts

### Regions and zones

The world is divided into **regions** (e.g. San Francisco Bay) and **zones** (sub-areas within a region, e.g. Raccoon Strait). Zones carry coordinates, hazard annotations, and references to external data sources (tide station IDs, NOAA NWS zone codes). See [Domain Model](domain-model.md).

### Sailor profiles

Scoring thresholds are profile-driven. Three built-in profiles — **School**, **Cruiser** (default), and **Racer** — define ideal wind ranges, wave limits, and penalty curves. The same forecast data scores differently for a beginner versus a racer.

### Sailability score

Each hourly slot gets a 0–100 sailability score composed of wind, gust, wave, visibility, and wind-against-tide components. Verdicts: **GO** (≥ 65), **MAYBE** (35–64), **NO-GO** (< 35).

### MCP tools

Eight tool functions (`list_regions`, `get_zone_forecast`, `compare_zones_in_region`, `best_sail_windows`, `get_active_warnings`, `explain_score`, `list_zones`, `list_profiles`) are exposed over stdio and HTTP/SSE so any MCP-compatible AI agent can query sailing conditions programmatically. See [Integrations](integrations.md).
