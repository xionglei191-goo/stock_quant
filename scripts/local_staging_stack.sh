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
export AI_QUANT_POSTGRES_HOST_PORT="${AI_QUANT_POSTGRES_HOST_PORT:-15432}"

# Host-side addresses for staging_acceptance.py (runs on the host, connects via localhost)
_HOST_POSTGRES_DSN="${AI_QUANT_POSTGRES_DSN:-postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:${AI_QUANT_POSTGRES_HOST_PORT}/ai_quant}"
_HOST_S3_ENDPOINT="${AI_QUANT_S3_ENDPOINT:-http://127.0.0.1:9000}"
_HOST_OPENSEARCH_URL="${AI_QUANT_OPENSEARCH_URL:-http://127.0.0.1:9200}"
_HOST_OTEL_ENDPOINT="${AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4318/v1/logs}"
_HOST_NEO4J_SYNC_TARGET="${AI_QUANT_NEO4J_SYNC_TARGET:-http://127.0.0.1:7474/db/neo4j/tx/commit}"
_HOST_NEO4J_HTTP_URL="${AI_QUANT_NEO4J_HTTP_URL:-http://127.0.0.1:7474}"
_HOST_QDRANT_SYNC_TARGET="${AI_QUANT_QDRANT_SYNC_TARGET:-http://127.0.0.1:6333}"
_HOST_OPENLINEAGE_TARGET="${AI_QUANT_OPENLINEAGE_TARGET:-http://127.0.0.1:5001}"
_HOST_MLFLOW_TRACKING_URI="${AI_QUANT_MLFLOW_TRACKING_URI:-http://127.0.0.1:5002}"
_HOST_SECRET_MANAGER_PROVIDER="${AI_QUANT_SECRET_MANAGER_PROVIDER:-local-development-metadata-only}"
_APP_OPENLINEAGE_TARGET="${AI_QUANT_APP_OPENLINEAGE_TARGET:-http://openlineage:5000/openlineage}"
_APP_MLFLOW_TRACKING_URI="${AI_QUANT_APP_MLFLOW_TRACKING_URI:-http://mlflow:5000/mlflow}"

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
export AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT="$_HOST_OTEL_ENDPOINT"
export AI_QUANT_NEO4J_SYNC_TARGET="$_HOST_NEO4J_SYNC_TARGET"
export AI_QUANT_NEO4J_HTTP_URL="$_HOST_NEO4J_HTTP_URL"
export AI_QUANT_QDRANT_SYNC_TARGET="$_HOST_QDRANT_SYNC_TARGET"
export AI_QUANT_OPENLINEAGE_TARGET="$_HOST_OPENLINEAGE_TARGET"
export AI_QUANT_MLFLOW_TRACKING_URI="$_HOST_MLFLOW_TRACKING_URI"
export AI_QUANT_SECRET_MANAGER_PROVIDER="$_HOST_SECRET_MANAGER_PROVIDER"

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
  --capacity-default-threshold-ms "${AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS:-2000}" \
  --record-readiness \
  --notify-missing

python3 scripts/local_backup_restore_drill.py \
  --artifact-prefix "$AI_QUANT_STAGING_ARTIFACT_PREFIX" \
  --record-readiness-url "$AI_QUANT_STAGING_URL"

python3 scripts/staging_governance_acceptance.py \
  "$AI_QUANT_STAGING_URL" \
  --artifact-prefix "$AI_QUANT_STAGING_ARTIFACT_PREFIX" \
  --record-readiness

python3 scripts/staging_security_acceptance.py \
  "$AI_QUANT_STAGING_URL" \
  --artifact-prefix "$AI_QUANT_STAGING_ARTIFACT_PREFIX" \
  --secret-manager-provider "$AI_QUANT_SECRET_MANAGER_PROVIDER"

python3 scripts/staging_otel_acceptance.py \
  "$AI_QUANT_STAGING_URL" \
  --otel-endpoint "$AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT" \
  --artifact-prefix "$AI_QUANT_STAGING_ARTIFACT_PREFIX" \
  --record-readiness

python3 scripts/staging_graph_vector_acceptance.py \
  "$AI_QUANT_STAGING_URL" \
  --neo4j-url "$AI_QUANT_NEO4J_SYNC_TARGET" \
  --qdrant-url "$AI_QUANT_QDRANT_SYNC_TARGET"

python3 scripts/staging_lineage_registry_acceptance.py \
  "$AI_QUANT_STAGING_URL" \
  --openlineage-target "$_APP_OPENLINEAGE_TARGET" \
  --mlflow-target "$_APP_MLFLOW_TRACKING_URI" \
  --openlineage-health-url "$AI_QUANT_OPENLINEAGE_TARGET" \
  --mlflow-health-url "$AI_QUANT_MLFLOW_TRACKING_URI" \
  --artifact-prefix "$AI_QUANT_STAGING_ARTIFACT_PREFIX"

python3 scripts/staging_vision_gate_acceptance.py \
  "$AI_QUANT_STAGING_URL" \
  --artifact-prefix "$AI_QUANT_STAGING_ARTIFACT_PREFIX" \
  --record-launch-checklist
