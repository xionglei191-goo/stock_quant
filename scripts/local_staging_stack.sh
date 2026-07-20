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
export AI_QUANT_STAGING_ARTIFACT_PREFIX="${AI_QUANT_STAGING_ARTIFACT_PREFIX:-artifact://staging-local}"
export AI_QUANT_POSTGRES_HOST_PORT="${AI_QUANT_POSTGRES_HOST_PORT:-15432}"
export AI_QUANT_S3_HOST_PORT="${AI_QUANT_S3_HOST_PORT:-9000}"
export AI_QUANT_S3_CONSOLE_HOST_PORT="${AI_QUANT_S3_CONSOLE_HOST_PORT:-9001}"
export AI_QUANT_OPENSEARCH_HOST_PORT="${AI_QUANT_OPENSEARCH_HOST_PORT:-9200}"
export AI_QUANT_OPENSEARCH_MONITOR_PORT="${AI_QUANT_OPENSEARCH_MONITOR_PORT:-9600}"
export AI_QUANT_NEO4J_HTTP_HOST_PORT="${AI_QUANT_NEO4J_HTTP_HOST_PORT:-7474}"
export AI_QUANT_NEO4J_BOLT_HOST_PORT="${AI_QUANT_NEO4J_BOLT_HOST_PORT:-7687}"
export AI_QUANT_QDRANT_HOST_PORT="${AI_QUANT_QDRANT_HOST_PORT:-6333}"
export AI_QUANT_QDRANT_GRPC_HOST_PORT="${AI_QUANT_QDRANT_GRPC_HOST_PORT:-6334}"
export AI_QUANT_OTEL_GRPC_HOST_PORT="${AI_QUANT_OTEL_GRPC_HOST_PORT:-4317}"
export AI_QUANT_OTEL_HOST_PORT="${AI_QUANT_OTEL_HOST_PORT:-4318}"
export AI_QUANT_OTEL_PROM_HOST_PORT="${AI_QUANT_OTEL_PROM_HOST_PORT:-8889}"
export AI_QUANT_OPENLINEAGE_HOST_PORT="${AI_QUANT_OPENLINEAGE_HOST_PORT:-5001}"
export AI_QUANT_MLFLOW_HOST_PORT="${AI_QUANT_MLFLOW_HOST_PORT:-5002}"
export AI_QUANT_CROSS_BROWSER_MATRIX="${AI_QUANT_CROSS_BROWSER_MATRIX:-artifacts/ui-cross-browser-matrix.example.json}"
export AI_QUANT_HOST_RESEARCH_REPORT_ROOT="${AI_QUANT_HOST_RESEARCH_REPORT_ROOT:-/home/xionglei/文档/6大投行研报汇总}"

# Host-side addresses for staging_acceptance.py (runs on the host, connects via localhost)
_HOST_POSTGRES_DSN="${AI_QUANT_POSTGRES_DSN:-postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:${AI_QUANT_POSTGRES_HOST_PORT}/ai_quant}"
_HOST_S3_ENDPOINT="${AI_QUANT_S3_ENDPOINT:-http://127.0.0.1:${AI_QUANT_S3_HOST_PORT}}"
_HOST_OPENSEARCH_URL="${AI_QUANT_OPENSEARCH_URL:-http://127.0.0.1:${AI_QUANT_OPENSEARCH_HOST_PORT}}"
_HOST_OTEL_ENDPOINT="${AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:${AI_QUANT_OTEL_HOST_PORT}/v1/logs}"
_HOST_NEO4J_SYNC_TARGET="${AI_QUANT_NEO4J_SYNC_TARGET:-http://127.0.0.1:${AI_QUANT_NEO4J_HTTP_HOST_PORT}/db/neo4j/tx/commit}"
_HOST_NEO4J_HTTP_URL="${AI_QUANT_NEO4J_HTTP_URL:-http://127.0.0.1:${AI_QUANT_NEO4J_HTTP_HOST_PORT}}"
_HOST_QDRANT_SYNC_TARGET="${AI_QUANT_QDRANT_SYNC_TARGET:-http://127.0.0.1:${AI_QUANT_QDRANT_HOST_PORT}}"
_HOST_OPENLINEAGE_TARGET="${AI_QUANT_OPENLINEAGE_TARGET:-http://127.0.0.1:${AI_QUANT_OPENLINEAGE_HOST_PORT}}"
_HOST_MLFLOW_TRACKING_URI="${AI_QUANT_MLFLOW_TRACKING_URI:-http://127.0.0.1:${AI_QUANT_MLFLOW_HOST_PORT}}"
_HOST_SECRET_MANAGER_PROVIDER="${AI_QUANT_SECRET_MANAGER_PROVIDER:-local-development-metadata-only}"
_APP_OPENLINEAGE_TARGET="${AI_QUANT_APP_OPENLINEAGE_TARGET:-http://openlineage:5000/openlineage}"
_APP_MLFLOW_TRACKING_URI="${AI_QUANT_APP_MLFLOW_TRACKING_URI:-http://mlflow:5000/mlflow}"

# Pin app-container settings explicitly so .env values intended for single-process
# local runs cannot switch the Compose app back to SQLite/local objects/local search.
export AI_QUANT_HOST="${AI_QUANT_APP_HOST:-0.0.0.0}"
export AI_QUANT_DB=""
export AI_QUANT_POSTGRES_DSN="${AI_QUANT_APP_POSTGRES_DSN:-postgresql://ai_quant:ai_quant_dev_password@postgres:5432/ai_quant}"
export AI_QUANT_OBJECT_STORE_BACKEND="${AI_QUANT_APP_OBJECT_STORE_BACKEND:-s3}"
export AI_QUANT_OBJECT_STORE="${AI_QUANT_APP_OBJECT_STORE:-/data/objects}"
export AI_QUANT_S3_ENDPOINT="${AI_QUANT_APP_S3_ENDPOINT:-http://minio:9000}"
export AI_QUANT_SEARCH_BACKEND="${AI_QUANT_APP_SEARCH_BACKEND:-opensearch}"
export AI_QUANT_OPENSEARCH_URL="${AI_QUANT_APP_OPENSEARCH_URL:-http://opensearch:9200}"
export AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT="${AI_QUANT_APP_OTEL_EXPORTER_OTLP_ENDPOINT:-http://otel-collector:4318/v1/logs}"
export AI_QUANT_NEO4J_SYNC_TARGET="${AI_QUANT_APP_NEO4J_SYNC_TARGET:-http://neo4j:7474/db/neo4j/tx/commit}"
export AI_QUANT_NEO4J_HTTP_URL="${AI_QUANT_APP_NEO4J_HTTP_URL:-http://neo4j:7474}"
export AI_QUANT_QDRANT_SYNC_TARGET="${AI_QUANT_APP_QDRANT_SYNC_TARGET:-http://qdrant:6333}"
export AI_QUANT_OPENLINEAGE_TARGET="${AI_QUANT_APP_OPENLINEAGE_HEALTH_TARGET:-http://openlineage:5000}"
export AI_QUANT_MLFLOW_TRACKING_URI="${AI_QUANT_APP_MLFLOW_HEALTH_TARGET:-http://mlflow:5000}"
export AI_QUANT_SECRET_MANAGER_PROVIDER="${AI_QUANT_APP_SECRET_MANAGER_PROVIDER:-local-development-metadata-only}"
export AI_QUANT_TDX_VIPDOC_PATH="${AI_QUANT_APP_TDX_VIPDOC_PATH:-/data/local/tdx/vipdoc}"
export AI_QUANT_RESEARCH_REPORT_ROOT="${AI_QUANT_APP_RESEARCH_REPORT_ROOT:-/data/local/research_reports}"
export AI_QUANT_S3_BUCKET="${AI_QUANT_S3_BUCKET:-ai-quant-local}"
export AI_QUANT_S3_ACCESS_KEY="${AI_QUANT_S3_ACCESS_KEY:-ai_quant_minio}"
export AI_QUANT_S3_SECRET_KEY="${AI_QUANT_S3_SECRET_KEY:-ai_quant_minio_secret}"

if [ "${AI_QUANT_STACK_REBUILD:-false}" = "true" ]; then
  "${COMPOSE[@]}" up -d --build
else
  "${COMPOSE[@]}" up -d
fi

wait_http_ok() {
  local name="$1"
  local url="$2"
  local retries="${3:-60}"
  local delay="${4:-2}"
  for i in $(seq 1 "$retries"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready."
      return 0
    fi
    if [ "$i" -eq "$retries" ]; then
      echo "$name did not become ready within $((retries * delay))s: $url" >&2
      return 1
    fi
    sleep "$delay"
  done
}

wait_http_any() {
  local name="$1"
  local url="$2"
  local retries="${3:-60}"
  local delay="${4:-2}"
  for i in $(seq 1 "$retries"); do
    local code
    code="$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' "$url" || true)"
    if [ "$code" != "000" ]; then
      echo "$name is ready."
      return 0
    fi
    if [ "$i" -eq "$retries" ]; then
      echo "$name did not become ready within $((retries * delay))s: $url" >&2
      return 1
    fi
    sleep "$delay"
  done
}

wait_tcp() {
  local name="$1"
  local host="$2"
  local port="$3"
  local retries="${4:-60}"
  local delay="${5:-2}"
  for i in $(seq 1 "$retries"); do
    if python3 - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys
host = sys.argv[1]
port = int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=1):
        pass
except OSError:
    raise SystemExit(1)
PY
    then
      echo "$name is ready."
      return 0
    fi
    if [ "$i" -eq "$retries" ]; then
      echo "$name did not become ready within $((retries * delay))s: ${host}:${port}" >&2
      return 1
    fi
    sleep "$delay"
  done
}

wait_tcp "PostgreSQL" 127.0.0.1 "$AI_QUANT_POSTGRES_HOST_PORT"
wait_http_ok "MinIO" "http://127.0.0.1:${AI_QUANT_S3_HOST_PORT}/minio/health/live"
wait_http_ok "OpenSearch" "http://127.0.0.1:${AI_QUANT_OPENSEARCH_HOST_PORT}"
wait_http_ok "Neo4j" "http://127.0.0.1:${AI_QUANT_NEO4J_HTTP_HOST_PORT}"
wait_http_ok "Qdrant" "http://127.0.0.1:${AI_QUANT_QDRANT_HOST_PORT}/readyz"
wait_http_any "OTel collector" "http://127.0.0.1:${AI_QUANT_OTEL_HOST_PORT}/"
wait_http_ok "OpenLineage" "http://127.0.0.1:${AI_QUANT_OPENLINEAGE_HOST_PORT}"
wait_http_ok "MLflow" "http://127.0.0.1:${AI_QUANT_MLFLOW_HOST_PORT}"

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
  --timeout "${AI_QUANT_STAGING_ACCEPTANCE_TIMEOUT_SECONDS:-60}" \
  --cross-browser-matrix "$AI_QUANT_CROSS_BROWSER_MATRIX" \
  --capacity-default-threshold-ms "${AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS:-2000}" \
  --capacity-simulate-threshold-ms "${AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS:-2000}" \
  --capacity-batch-threshold-ms "${AI_QUANT_STAGING_CAPACITY_BATCH_THRESHOLD_MS:-60000}" \
  --capacity-setup-threshold-ms "${AI_QUANT_STAGING_CAPACITY_SETUP_THRESHOLD_MS:-20000}" \
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
  --timeout "${AI_QUANT_STAGING_ACCEPTANCE_TIMEOUT_SECONDS:-60}" \
  --record-launch-checklist
