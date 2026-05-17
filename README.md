# California Sail — Sailing Conditions Forecast

A Streamlit + Plotly app that answers three questions for sailors:

1. **Go or No-Go?** — Is it safe and enjoyable to sail right now?
2. **Where?** — Which zone in the region has the best conditions today? *(Phase 2)*
3. **When?** — What is the best 3-hour window today or tomorrow?

**Regions covered:** San Francisco Bay · Puget Sound (Seattle) · Sardinia

**Data source:** [Open-Meteo](https://open-meteo.com/) — free, no API key required.

---

## Run locally

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app from the project root
streamlit run app/app.py
```

Then open http://localhost:8501 in your browser.

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed (the app reads from environment variables):

| Variable | Default | Description |
|---|---|---|
| `TIMEZONE_DEFAULT` | `America/Los_Angeles` | Display timezone fallback |
| `FORECAST_DAYS` | `7` | Number of forecast days (1–16) |
| `HTTP_TIMEOUT_SECONDS` | `8` | API request timeout |
| `HTTP_RETRIES` | `2` | Retry count on 5xx errors |
| `CACHE_TTL_SECONDS` | `900` | Streamlit cache TTL (15 min) |

---

## Project structure

```
california_sail/
  app/
    app.py              # Streamlit entry point
    domain/
      regions.py        # SailingRegion + SailingZone dataclasses, YAML loader
      units.py          # m/s → kt, deg → compass, angular helpers
      normalize.py      # API response → canonical hourly DataFrame
      scoring.py        # Sailability score (v1), best_windows, verdict
    infra/
      config.py         # Configuration (defaults + env)
      http.py           # HTTP session with retries
      cache.py          # TTL cache
      logging.py        # Logging setup
      open_meteo_client.py  # Open-Meteo weather forecast client
    services/
      forecast_service.py   # Orchestration: fetch → normalize → score
    viz/
      themes.py         # Plotly LAYOUT_DEFAULTS, Sailability colour scale
      charts.py         # Chart builders: wind rose, wind timeline, sailability ribbon
    ui/
      layout.py         # Streamlit page layout
      components.py     # Reusable UI components
  data/
    sailing_areas.yaml  # Regions and zones definition
  tests/
    fixtures/           # Recorded API responses for offline testing
    test_regions.py
    test_units.py
    test_scoring.py
    test_normalize.py
    test_open_meteo_client.py
    test_forecast_service.py
    test_charts.py
    test_config.py
```

---

## Sailability score (Phase 1 — cruiser baseline)

The **Sailability score (0–100)** answers: *"How good is this hour for a relaxed cruising sail?"*

### Hard safety gates (any failure → score capped at ≤ 25)

| Gate | Threshold |
|---|---|
| Wind gust | > 30 kt → **No-Go** |
| Visibility | < 1 km → **No-Go** |

### Scoring components

| Component | Weight | Formula |
|---|---|---|
| Wind score | 55% | Gaussian peak at 14 kt (ideal range 10–18 kt, σ = 8 kt) |
| Visibility score | 45% | Linear: 100 at ≥ 10 km, 0 at 1 km |

```
sailability = 0.55 × wind_score + 0.45 × visibility_score
(capped at 25 if any hard gate fails)
```

### Verdict thresholds

| Score | Verdict |
|---|---|
| ≥ 65 | **GO** ✅ |
| 35–64 | **MAYBE** ⚠️ |
| < 35 | **NO-GO** 🚫 |

> **Phase 2** will add: sea state (wave height + chop penalty), tidal currents, wind-against-tide penalty.
> **Phase 3** will add: sailor profile selection (School / Cruiser / Racer) with profile-driven thresholds.

---

## Sailing areas

Regions and zones are defined in `data/sailing_areas.yaml`.

**Phase 1 (current):** one default zone per region.

| Region | Default zone | Timezone |
|---|---|---|
| San Francisco Bay | City Front | America/Los_Angeles |
| Puget Sound (Seattle) | Shilshole Bay | America/Los_Angeles |
| Sardinia | Costa Smeralda | Europe/Rome |

**Phase 2:** will expand to 3–4 zones per region for zone-comparison.

---

## Tests

```bash
pytest tests/ -v
```

Tests cover: region loader and validation, unit conversions, scoring boundary cases, Open-Meteo client contract (fixture-based, no live API), forecast service orchestration (mocked), and chart builder smoke tests.

---

## Docker (local only)

```bash
docker build -t california-sail .
docker run -p 8501:8501 california-sail
```

Then open http://localhost:8501.

---

## Deploy on Streamlit Community Cloud

1. Push this repository to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app** → set **Main file path** to `app/app.py`.
4. Click **Deploy**.

The app will be available at a public URL immediately after the first build.
