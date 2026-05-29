# Deployment — Google Cloud Run

California Sail runs as two Cloud Run services in project `sermolin-2026`, region `us-west1`.

---

## Infrastructure overview

```
GCP project: sermolin-2026 / region: us-west1
──────────────────────────────────────────────────────────────────
Artifact Registry repo:  california-sail
  └── us-west1-docker.pkg.dev/sermolin-2026/california-sail/

Cloud Run services:
  california-sail-ui   ← Streamlit UI  (Dockerfile.ui)
  california-sail-api  ← FastAPI/bot   (Dockerfile.api)

Secret Manager:
  TELEGRAM_BOT_TOKEN   ← read by california-sail-api

Cloud Build:
  cloudbuild.ui.yaml   ← builds Dockerfile.ui
  cloudbuild.api.yaml  ← builds Dockerfile.api
──────────────────────────────────────────────────────────────────
```

---

## Services

### `california-sail-ui`

| Property | Value |
|---|---|
| Image | `Dockerfile.ui` |
| Port | 8501 |
| Memory | 512 Mi |
| Command | `streamlit run app/app.py` |
| Env vars | None (uses Open-Meteo / NOAA directly, no keys needed) |
| Auth | Allow unauthenticated |

Public URL: `https://california-sail-ui-<hash>-uw.a.run.app`

### `california-sail-api`

| Property | Value |
|---|---|
| Image | `Dockerfile.api` |
| Port | 8080 |
| Memory | 512 Mi |
| Command | `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT` |
| Env vars | `WEBHOOK_URL` (set automatically by deploy script), secret `TELEGRAM_BOT_TOKEN` |
| Auth | Allow unauthenticated |

Public URL: `https://california-sail-api-<hash>-uw.a.run.app`

The API service mounts the MCP SSE transport at `/mcp/sse`.

---

## Dockerfiles

### `Dockerfile.ui`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8501
EXPOSE $PORT
CMD ["sh", "-c", "streamlit run app/app.py --server.port $PORT --server.address 0.0.0.0 --server.fileWatcherType none"]
```

Key points:
- `--server.fileWatcherType none` disables the file watcher (irrelevant in containers, saves CPU).
- Cloud Run sets `PORT` automatically; the Dockerfile provides a default so it also works locally.

### `Dockerfile.api`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
EXPOSE $PORT
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port $PORT"]
```

---

## Cloud Build configs

Both configs follow the same pattern: a single `docker build` step with the image name injected via `_IMAGE` substitution.

### `cloudbuild.ui.yaml`

```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-f', 'Dockerfile.ui', '-t', '$_IMAGE', '.']
images:
  - '$_IMAGE'
```

### `cloudbuild.api.yaml`

```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-f', 'Dockerfile.api', '-t', '$_IMAGE', '.']
images:
  - '$_IMAGE'
```

---

## Deploy script — `scripts/deploy.sh`

The script handles end-to-end build and deploy for either service.

```
Usage: ./scripts/deploy.sh [ui|api|both]
       Default: both
```

### What it does

1. Computes a short Git SHA tag (e.g. `a1b2c3d`) for the image.
2. Calls `gcloud builds submit --config cloudbuild.<service>.yaml --substitutions "_IMAGE=<registry>/<service>:<tag>" .` to build the image in Cloud Build and push it to Artifact Registry.
3. Calls `gcloud run deploy <service> --image <image> --region us-west1 ...` to deploy to Cloud Run.
4. For the API: reads back the service URL and updates `WEBHOOK_URL` env var with another `gcloud run services update` call.
5. Prints both service URLs at the end.

### Full deploy (both services)

```bash
./scripts/deploy.sh
# or explicitly:
./scripts/deploy.sh both
```

### Deploy UI only

```bash
./scripts/deploy.sh ui
```

### Deploy API only

```bash
./scripts/deploy.sh api
```

---

## First-time GCP setup

These steps only need to be run once per GCP project.

### 1. Install and authenticate gcloud

```bash
# Install (macOS without Homebrew)
curl https://sdk.cloud.google.com | bash
# Then re-source shell or open a new terminal

# Set Python 3.11 for gcloud (if your system Python is 3.9):
echo 'export CLOUDSDK_PYTHON=/usr/local/bin/python3.11' >> ~/.zshrc
source ~/.zshrc

# Authenticate
gcloud auth login
gcloud config set project sermolin-2026
gcloud config set compute/region us-west1
```

### 2. Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  --project=sermolin-2026
```

### 3. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create california-sail \
  --repository-format=docker \
  --location=us-west1 \
  --project=sermolin-2026
```

### 4. Authenticate Docker to Artifact Registry

```bash
gcloud auth configure-docker us-west1-docker.pkg.dev
```

### 5. Store the Telegram bot token in Secret Manager

```bash
# Create the secret (first time only)
gcloud secrets create TELEGRAM_BOT_TOKEN --project=sermolin-2026

# Add the secret value
echo -n "<your-bot-token>" | \
  gcloud secrets versions add TELEGRAM_BOT_TOKEN --data-file=- --project=sermolin-2026
```

### 6. Grant the compute service account access to the secret

```bash
PROJECT_NUMBER=$(gcloud projects describe sermolin-2026 --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding TELEGRAM_BOT_TOKEN \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=sermolin-2026
```

### 7. Run the deploy script

```bash
./scripts/deploy.sh
```

---

## Updating the deployment

After any code change:

```bash
# Rebuild and redeploy both services
./scripts/deploy.sh

# Or just the changed service:
./scripts/deploy.sh ui
./scripts/deploy.sh api
```

---

## Telegram webhook

The Telegram webhook is registered automatically by the API service at startup when `WEBHOOK_URL` is set. The deploy script sets this variable to the Cloud Run service URL after each deploy.

To manually trigger a webhook re-registration (e.g. after a URL change):

```bash
gcloud run services update california-sail-api \
  --region us-west1 \
  --project sermolin-2026 \
  --update-env-vars NO_OP=$(date +%s)
```

This forces a new revision (and therefore a new lifespan startup) without changing any other config.

To inspect the current webhook:

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

---

## Environment variables in Cloud Run

Variables are set via `--set-env-vars` in the deploy script. Secrets are injected with `--set-secrets`. To update a variable without a full redeploy:

```bash
gcloud run services update california-sail-api \
  --region us-west1 \
  --project sermolin-2026 \
  --update-env-vars KEY=VALUE
```

---

## Cost notes

- Both Cloud Run services use the free tier for low traffic (0 requests when idle = $0).
- Cloud Build: first 120 build-minutes/day are free; each full deploy takes ~2 minutes.
- Secret Manager: first 6 secret versions/month are free.
- Artifact Registry: first 0.5 GB storage is free.
- Open-Meteo, NOAA CO-OPS, and NOAA NWS are all free with no API keys.
