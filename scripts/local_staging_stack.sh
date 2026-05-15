#!/usr/bin/env bash
set -euo pipefail

if command -v docker >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v podman >/dev/null 2>&1; then
  COMPOSE=(podman compose)
else
  echo "Docker or Podman is required to start the local staging stack." >&2
  echo "Install Docker Desktop/Engine or Podman, then rerun: bash scripts/local_staging_stack.sh" >&2
  exit 127
fi

export AI_QUANT_STAGING_URL="${AI_QUANT_STAGING_URL:-http://127.0.0.1:8000}"
export AI_QUANT_STAGING_ARTIFACT_PREFIX="${AI_QUANT_STAGING_ARTIFACT_PREFIX:-artifact://local-staging}"

# Host-side addresses for staging_acceptance.py (runs on the host, connects via localhost)
_HOST_POSTGRES_DSN="${AI_QUANT_POSTGRES_DSN:-postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:5432/ai_quant}"
_HOST_S3_ENDPOINT="${AI_QUANT_S3_ENDPOINT:-http://127.0.0.1:9000}"
_HOST_OPENSEARCH_URL="${AI_QUANT_OPENSEARCH_URL:-http://127.0.0.1:9200}"

# These are only needed by the acceptance script on the host; do NOT export them
# so docker-compose.yml container defaults (postgres:5432, minio:9000, etc.) are used.
export AI_QUANT_S3_BUCKET="${AI_QUANT_S3_BUCKET:-ai-quant-local}"
export AI_QUANT_S3_ACCESS_KEY="${AI_QUANT_S3_ACCESS_KEY:-ai_quant_minio}"
export AI_QUANT_S3_SECRET_KEY="${AI_QUANT_S3_SECRET_KEY:-ai_quant_minio_secret}"

# Unset service URLs that would override docker-compose container defaults
unset AI_QUANT_POSTGRES_DSN AI_QUANT_DB AI_QUANT_S3_ENDPOINT AI_QUANT_OPENSEARCH_URL \
      AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT AI_QUANT_NEO4J_SYNC_TARGET AI_QUANT_NEO4J_HTTP_URL \
      AI_QUANT_QDRANT_SYNC_TARGET AI_QUANT_OPENLINEAGE_TARGET AI_QUANT_MLFLOW_TRACKING_URI \
      AI_QUANT_SECRET_MANAGER_PROVIDER 2>/dev/null || true

"${COMPOSE[@]}" up -d --build

export AI_QUANT_POSTGRES_DSN="$_HOST_POSTGRES_DSN"
export AI_QUANT_S3_ENDPOINT="$_HOST_S3_ENDPOINT"
export AI_QUANT_OPENSEARCH_URL="$_HOST_OPENSEARCH_URL"

# Wait for the app to be healthy before running acceptance
echo "Waiting for app to be ready at $AI_QUANT_STAGING_URL ..."
for i in $(seq 1 60); do
  if curl -fsS "$AI_QUANT_STAGING_URL/api/health" >/dev/null 2>&1; then
    echo "App is ready."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "App did not become ready within 60s. Check: docker logs sotck_quant-ai-quant-org-1" >&2
    exit 1
  fi
  sleep 2
done

python3 scripts/staging_acceptance.py \
  "$AI_QUANT_STAGING_URL" \
  --artifact-prefix "$AI_QUANT_STAGING_ARTIFACT_PREFIX" \
  --record-readiness \
  --notify-missing
