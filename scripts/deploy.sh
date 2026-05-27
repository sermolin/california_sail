#!/usr/bin/env bash
# deploy.sh — build and deploy both California Sail services to Cloud Run
#
# Prerequisites (run once, not part of this script):
#   1. gcloud auth login && gcloud auth configure-docker us-west1-docker.pkg.dev
#   2. Create Artifact Registry repo:
#        gcloud artifacts repositories create california-sail \
#          --repository-format=docker \
#          --location=us-west1 \
#          --project=sermolin-2026
#   3. Store the Telegram bot token in Secret Manager:
#        gcloud secrets create TELEGRAM_BOT_TOKEN \
#          --project=sermolin-2026
#        echo -n "YOUR_TOKEN" | \
#          gcloud secrets versions add TELEGRAM_BOT_TOKEN --data-file=- \
#          --project=sermolin-2026
#   4. Grant Cloud Run service account access to the secret:
#        PROJECT_NUMBER=$(gcloud projects describe sermolin-2026 --format='value(projectNumber)')
#        gcloud secrets add-iam-policy-binding TELEGRAM_BOT_TOKEN \
#          --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
#          --role="roles/secretmanager.secretAccessor" \
#          --project=sermolin-2026
#
# Usage:
#   ./scripts/deploy.sh            # deploy both services
#   ./scripts/deploy.sh ui         # deploy only the Streamlit UI
#   ./scripts/deploy.sh api        # deploy only the FastAPI service
#
set -euo pipefail

PROJECT_ID="sermolin-2026"
REGION="us-west1"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/california-sail"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"

TARGET="${1:-both}"

# ---------------------------------------------------------------------------
# Build and push an image, then deploy to Cloud Run
# ---------------------------------------------------------------------------

deploy_ui() {
  echo "==> Building UI image (tag: ${TAG})"
  IMAGE="${REGISTRY}/california-sail-ui:${TAG}"
  gcloud builds submit \
    --config cloudbuild.ui.yaml \
    --substitutions "_IMAGE=${IMAGE}" \
    --project "${PROJECT_ID}" \
    .

  echo "==> Deploying california-sail-ui to Cloud Run"
  gcloud run deploy california-sail-ui \
    --image "${IMAGE}" \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --platform managed \
    --allow-unauthenticated \
    --port 8501 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 3
}

deploy_api() {
  echo "==> Building API image (tag: ${TAG})"
  IMAGE="${REGISTRY}/california-sail-api:${TAG}"
  gcloud builds submit \
    --config cloudbuild.api.yaml \
    --substitutions "_IMAGE=${IMAGE}" \
    --project "${PROJECT_ID}" \
    .

  echo "==> Deploying california-sail-api to Cloud Run"
  gcloud run deploy california-sail-api \
    --image "${IMAGE}" \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 5 \
    --set-env-vars "PYTHONPATH=/app" \
    --update-secrets "TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest"

  # Retrieve the deployed service URL and register it as WEBHOOK_URL
  SERVICE_URL=$(gcloud run services describe california-sail-api \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --format "value(status.url)")

  echo "==> Service URL: ${SERVICE_URL}"
  echo "==> Updating WEBHOOK_URL env var to ${SERVICE_URL}"
  gcloud run services update california-sail-api \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --update-env-vars "WEBHOOK_URL=${SERVICE_URL}"

  echo "==> Telegram webhook will be registered automatically on next service startup."
  echo "    To trigger a restart: gcloud run services update california-sail-api --region ${REGION} --project ${PROJECT_ID} --update-env-vars NO_OP=$(date +%s)"
}

case "${TARGET}" in
  ui)   deploy_ui ;;
  api)  deploy_api ;;
  both) deploy_ui; deploy_api ;;
  *)
    echo "Usage: $0 [ui|api|both]"
    exit 1
    ;;
esac

echo ""
echo "==> Done."
echo "    UI:  $(gcloud run services describe california-sail-ui --region ${REGION} --project ${PROJECT_ID} --format 'value(status.url)' 2>/dev/null || echo '(not deployed yet)')"
echo "    API: $(gcloud run services describe california-sail-api --region ${REGION} --project ${PROJECT_ID} --format 'value(status.url)' 2>/dev/null || echo '(not deployed yet)')"
