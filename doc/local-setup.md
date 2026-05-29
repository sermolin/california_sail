# Local Development Setup

This document walks through setting up a full local development environment from a fresh clone.

---

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Python | 3.10 | `mcp[cli]` requires Python ≥ 3.10. Tested on 3.11. |
| Git | any | — |
| Docker Desktop | 4.x | Optional — only needed for the full `docker compose` stack |
| `gcloud` CLI | 460+ | Optional — only needed for GCP deployments |

Check your Python version:

```bash
python3 --version   # must be 3.10+
# or, if you use pyenv / asdf:
python3.11 --version
```

---

## 1. Clone and set up

```bash
git clone <repo-url> california_sail
cd california_sail

# Automated setup (creates .venv, installs deps, copies .env.example → .env)
./setup.sh
```

`setup.sh` does exactly this:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

If you prefer to do it manually:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## 2. Environment variables

All configuration is in `.env` (copied from `.env.example`). The Streamlit UI works without any changes to the defaults.

Edit `.env` to taste:

```ini
# ── Runtime config ──────────────────────────────────────────────
TIMEZONE_DEFAULT=America/Los_Angeles
FORECAST_DAYS=7           # 1–16
HTTP_TIMEOUT_SECONDS=8
HTTP_RETRIES=2
CACHE_TTL_SECONDS=900     # 15 minutes

# ── Telegram bot ─────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=       # required to run the bot
WEBHOOK_URL=              # leave blank for local polling mode

# ── Slack bot ────────────────────────────────────────────────────
SLACK_BOT_TOKEN=          # xoxb-…
SLACK_SIGNING_SECRET=

# ── NL agent (OpenRouter) ────────────────────────────────────────
OPENROUTER_API_KEY=
OPENROUTER_MODEL=anthropic/claude-3-haiku
AGENT_MAX_HISTORY=20
AGENT_TTL_MINUTES=30
```

The application loads `.env` automatically using `python-dotenv` (called from `app/infra/config.py` and the bot entry points).

---

## 3. Running the Streamlit UI

```bash
./run.sh
# or:
source .venv/bin/activate
streamlit run app/app.py
```

Open http://localhost:8501. The UI makes calls to Open-Meteo and NOAA directly from the browser process — no API keys needed.

---

## 4. Running the FastAPI backend

```bash
source .venv/bin/activate
uvicorn app.api.main:app --reload --port 8080
```

Endpoints available locally:
- `GET http://localhost:8080/health`
- `POST http://localhost:8080/telegram/webhook`
- `POST http://localhost:8080/slack/events`
- `GET http://localhost:8080/mcp/sse` (MCP SSE transport)

---

## 5. Running the Telegram bot (polling mode)

In polling mode the bot does not need a public URL — it long-polls Telegram's servers directly. This is the recommended local development mode.

```bash
source .venv/bin/activate
TELEGRAM_BOT_TOKEN=<your-token> python -m app.bot.telegram
```

Or set `TELEGRAM_BOT_TOKEN` in `.env` and just run:

```bash
python -m app.bot.telegram
```

The bot listens until you press Ctrl+C.

---

## 6. Running the MCP server (stdio mode)

The MCP server in stdio mode is intended for use with Cursor or Claude Desktop.

```bash
source .venv/bin/activate
python -m app.mcp.server
```

For the HTTP/SSE transport (useful for testing from curl or a browser):

```bash
python -m app.mcp.server --transport sse --port 8765
# Then: http://localhost:8765/sse
```

See [Integrations — MCP server](integrations.md#mcp-server) for Cursor / Claude Desktop configuration.

---

## 7. Running the full stack with Docker Compose

Docker Compose starts both services with a single command. Useful for integration testing.

```bash
docker compose up           # foreground
docker compose up -d        # background
```

| Service | URL | Notes |
|---|---|---|
| UI | http://localhost:8501 | Streamlit |
| API | http://localhost:8080 | FastAPI; MCP SSE at `/mcp/sse` |

Both services read `.env`. `WEBHOOK_URL` should be left blank (or absent) in the local compose file so the API starts without trying to register a Telegram webhook.

To rebuild images after code changes:

```bash
docker compose build && docker compose up
```

---

## 8. Running the test suite

```bash
source .venv/bin/activate
pytest
```

Run a specific module:

```bash
pytest tests/test_scoring.py -v
```

Run with coverage:

```bash
pytest --cov=app --cov-report=term-missing
```

See [Testing](testing.md) for the full test matrix and fixture details.

---

## 9. Adding a new sailing region

1. Edit `data/sailing_areas.yaml` — add a new entry under `regions`.
2. For each zone:
   - Find the NOAA CO-OPS station ID at https://tidesandcurrents.noaa.gov/map (US only).
   - Find the NOAA NWS marine zone at https://www.weather.gov/gis/MarineZones (US only).
   - Set both to `null` for non-US regions.
3. If the region has no NOAA coverage, `app/domain/warnings.py → synthesize_warnings()` will automatically generate warnings from the forecast data.
4. Run the test suite to verify YAML loading and scoring:
   ```bash
   pytest tests/test_regions.py tests/test_forecast_service.py -v
   ```

---

## 10. Project structure quick reference

```
.venv/            Python virtual environment (not in git)
app/              Application source (see modules.md)
data/             YAML config files
doc/              Developer documentation (you are here)
examples/mcp/     Cursor / Claude Desktop MCP config snippets
scripts/          deploy.sh
tests/            pytest test suite
.env              Local secrets (not in git)
.env.example      Template
docker-compose.yml
Dockerfile.ui
Dockerfile.api
pyproject.toml
requirements.txt
run.sh            ./run.sh → streamlit run app/app.py
setup.sh          ./setup.sh → one-shot environment setup
```
