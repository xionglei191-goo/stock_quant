#!/usr/bin/env bash
set -euo pipefail

if [ ! -f "docker-compose.yml" ]; then
  echo "Run this script from the repository root." >&2
  exit 2
fi

# Keep the personal-production stack on ports that are less likely to collide
# with common local PostgreSQL/MinIO/OpenSearch/Neo4j/Qdrant installs.
export AI_QUANT_STAGING_URL="${AI_QUANT_STAGING_URL:-http://127.0.0.1:8000}"
export AI_QUANT_STAGING_ARTIFACT_PREFIX="${AI_QUANT_STAGING_ARTIFACT_PREFIX:-artifact://staging-local}"
export AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS="${AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS:-5000}"
export AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS="${AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS:-5000}"
export AI_QUANT_POSTGRES_HOST_PORT="${AI_QUANT_POSTGRES_HOST_PORT:-15432}"
export AI_QUANT_S3_HOST_PORT="${AI_QUANT_S3_HOST_PORT:-19000}"
export AI_QUANT_S3_CONSOLE_HOST_PORT="${AI_QUANT_S3_CONSOLE_HOST_PORT:-19001}"
export AI_QUANT_OPENSEARCH_HOST_PORT="${AI_QUANT_OPENSEARCH_HOST_PORT:-19200}"
export AI_QUANT_OPENSEARCH_MONITOR_PORT="${AI_QUANT_OPENSEARCH_MONITOR_PORT:-19600}"
export AI_QUANT_NEO4J_HTTP_HOST_PORT="${AI_QUANT_NEO4J_HTTP_HOST_PORT:-17474}"
export AI_QUANT_NEO4J_BOLT_HOST_PORT="${AI_QUANT_NEO4J_BOLT_HOST_PORT:-17687}"
export AI_QUANT_QDRANT_HOST_PORT="${AI_QUANT_QDRANT_HOST_PORT:-16333}"
export AI_QUANT_QDRANT_GRPC_HOST_PORT="${AI_QUANT_QDRANT_GRPC_HOST_PORT:-16334}"
export AI_QUANT_OTEL_GRPC_HOST_PORT="${AI_QUANT_OTEL_GRPC_HOST_PORT:-14317}"
export AI_QUANT_OTEL_HOST_PORT="${AI_QUANT_OTEL_HOST_PORT:-14318}"
export AI_QUANT_OTEL_PROM_HOST_PORT="${AI_QUANT_OTEL_PROM_HOST_PORT:-18889}"
export AI_QUANT_OPENLINEAGE_HOST_PORT="${AI_QUANT_OPENLINEAGE_HOST_PORT:-15001}"
export AI_QUANT_MLFLOW_HOST_PORT="${AI_QUANT_MLFLOW_HOST_PORT:-15002}"

bash scripts/local_staging_stack.sh

PYTHON_BIN="${AI_QUANT_LOCAL_PYTHON:-python3}"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

"$PYTHON_BIN" scripts/local_production_audit.py \
  --base-url "$AI_QUANT_STAGING_URL" \
  --output artifacts/local-production-audit.json

if [ "${AI_QUANT_LOCAL_PRODUCTION_SKIP_AI_ACCEPTANCE:-false}" = "true" ]; then
  echo "Skipping local AI capability acceptance because AI_QUANT_LOCAL_PRODUCTION_SKIP_AI_ACCEPTANCE=true."
elif "$PYTHON_BIN" - "$AI_QUANT_STAGING_URL" <<'PY'
import json
import sys
from urllib.request import urlopen

base_url = sys.argv[1].rstrip("/")
health = json.load(urlopen(f"{base_url}/api/health", timeout=10))
data = health.get("data", health)
llm = data.get("llm_gateway", {}) if isinstance(data, dict) else {}
ocr = data.get("document_parser", {}) if isinstance(data, dict) else {}
raise SystemExit(0 if llm.get("configured") and ocr.get("configured") else 1)
PY
then
  "$PYTHON_BIN" scripts/local_ai_capability_acceptance.py \
    --base-url "$AI_QUANT_STAGING_URL" \
    --output artifacts/local-ai-capability-acceptance.json
else
  echo "Skipping local AI capability acceptance because LLM or PaddleOCR-VL is not configured."
fi

echo "Local personal-production stack is ready at $AI_QUANT_STAGING_URL"
