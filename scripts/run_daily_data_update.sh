#!/usr/bin/env bash
set -euo pipefail

if [ ! -f "docker-compose.yml" ]; then
  echo "Run this script from the repository root." >&2
  exit 2
fi

bool_enabled() {
  case "${1,,}" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

if command -v docker >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v podman >/dev/null 2>&1; then
  COMPOSE=(podman compose)
else
  echo "Docker or Podman is required for the default compose runner." >&2
  echo "Set AI_QUANT_DAILY_RUNNER=host only if host Python has all required dependencies." >&2
  exit 127
fi

RUNNER="${AI_QUANT_DAILY_RUNNER:-compose}"
SERVICE="${AI_QUANT_DAILY_COMPOSE_SERVICE:-ai-quant-org}"
RUN_DATE="${AI_QUANT_DAILY_RUN_DATE:-$(date +%F)}"
END_DATE="${AI_QUANT_DAILY_END_DATE:-}"
RUN_ID="${AI_QUANT_DAILY_RUN_ID:-${RUN_DATE}-$(date +%H%M%S)}"
OUTPUT_BASE="${AI_QUANT_DAILY_OUTPUT_BASE:-artifacts/daily-update-local}"
OUTPUT_DIR="${AI_QUANT_DAILY_OUTPUT_DIR:-${OUTPUT_BASE%/}/runs/${RUN_ID}}"
STATE_FILE="${AI_QUANT_DAILY_STATE_FILE:-${OUTPUT_BASE%/}/state.json}"
LATEST_POINTER="${AI_QUANT_DAILY_LATEST_POINTER:-${OUTPUT_BASE%/}/latest-run.json}"
LOCK_FILE="${AI_QUANT_DAILY_LOCK_FILE:-${OUTPUT_BASE%/}/.daily-update.lock}"
mkdir -p "$(dirname "$STATE_FILE")" "$OUTPUT_DIR"

if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    echo "Daily update is already running; lock=$LOCK_FILE" >&2
    exit 75
  fi
fi

HOST_BASE_URL="${AI_QUANT_DAILY_HOST_BASE_URL:-${AI_QUANT_STAGING_URL:-http://127.0.0.1:8000}}"
CONTAINER_BASE_URL="${AI_QUANT_DAILY_CONTAINER_BASE_URL:-http://127.0.0.1:8000}"
HOST_DSN="${AI_QUANT_DAILY_HOST_DSN:-postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:${AI_QUANT_POSTGRES_HOST_PORT:-15432}/ai_quant}"
CONTAINER_DSN="${AI_QUANT_DAILY_CONTAINER_DSN:-postgresql://ai_quant:ai_quant_dev_password@postgres:5432/ai_quant}"
CONTAINER_VIPDOC_PATH="${AI_QUANT_DAILY_CONTAINER_VIPDOC_PATH:-/data/local/tdx/vipdoc}"
HOST_VIPDOC_PATH="${AI_QUANT_DAILY_HOST_VIPDOC_PATH:-data/local/tdx/vipdoc}"

RUN_ASHARE_INCREMENTAL="${AI_QUANT_DAILY_RUN_ASHARE_INCREMENTAL:-true}"
RUN_ASHARE_SCOPE_REFRESH="${AI_QUANT_DAILY_RUN_ASHARE_SCOPE_REFRESH:-true}"
ASHARE_BATCH_SIZE="${AI_QUANT_DAILY_ASHARE_BATCH_SIZE:-300}"
ASHARE_OFFSET="${AI_QUANT_DAILY_ASHARE_OFFSET:-}"
RUN_US_INCREMENTAL_FROM_DB="${AI_QUANT_DAILY_US_TICKERS_FROM_DB:-true}"
RUN_US_SCOPE_REFRESH="${AI_QUANT_DAILY_RUN_US_SCOPE_REFRESH:-true}"
US_BATCH_SIZE="${AI_QUANT_DAILY_US_BATCH_SIZE:-300}"
US_OFFSET="${AI_QUANT_DAILY_US_OFFSET:-}"
RUN_TDX_INCREMENTAL="${AI_QUANT_DAILY_TDX_INCREMENTAL:-false}"
ALLOW_IMPORT_FAILURE="${AI_QUANT_DAILY_ALLOW_IMPORT_FAILURE:-true}"
ALLOW_LATEST_ANALYSIS_FAILURE="${AI_QUANT_DAILY_ALLOW_LATEST_ANALYSIS_FAILURE:-false}"
RUN_PROJECT_COMPLETION_AUDIT="${AI_QUANT_DAILY_RUN_PROJECT_COMPLETION_AUDIT:-false}"
SKIP_ASHARE="${AI_QUANT_DAILY_SKIP_ASHARE:-false}"
SKIP_US="${AI_QUANT_DAILY_SKIP_US:-false}"
SKIP_TDX_COVERAGE_AUDIT="${AI_QUANT_DAILY_SKIP_TDX_COVERAGE_AUDIT:-false}"
SKIP_RESEARCH_BINDING="${AI_QUANT_DAILY_SKIP_RESEARCH_BINDING:-false}"
SKIP_LATEST_ANALYSIS="${AI_QUANT_DAILY_SKIP_LATEST_ANALYSIS:-false}"
SKIP_LOCAL_PRODUCTION_AUDIT="${AI_QUANT_DAILY_SKIP_LOCAL_PRODUCTION_AUDIT:-false}"
SKIP_PROJECT_COMPLETION_AUDIT="${AI_QUANT_DAILY_SKIP_PROJECT_COMPLETION_AUDIT:-false}"

wait_app() {
  local url="$1"
  for i in $(seq 1 90); do
    if curl -fsS "${url%/}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    if [ "$i" -eq 90 ]; then
      echo "App did not become ready within 180s: ${url%/}/api/health" >&2
      return 1
    fi
    sleep 2
  done
}

if [ "$RUNNER" = "compose" ]; then
  if bool_enabled "${AI_QUANT_DAILY_REBUILD:-false}"; then
    "${COMPOSE[@]}" up -d --build
  else
    "${COMPOSE[@]}" up -d
  fi
  wait_app "$HOST_BASE_URL"
  PIPELINE_DSN="$CONTAINER_DSN"
  PIPELINE_BASE_URL="$CONTAINER_BASE_URL"
  PIPELINE_VIPDOC_PATH="$CONTAINER_VIPDOC_PATH"
  PYTHON_RUN=("${COMPOSE[@]}" exec -T "$SERVICE" python)
elif [ "$RUNNER" = "host" ]; then
  wait_app "$HOST_BASE_URL"
  PIPELINE_DSN="$HOST_DSN"
  PIPELINE_BASE_URL="$HOST_BASE_URL"
  PIPELINE_VIPDOC_PATH="$HOST_VIPDOC_PATH"
  PYTHON_RUN=(python3)
else
  echo "Unsupported AI_QUANT_DAILY_RUNNER=$RUNNER; expected compose or host." >&2
  exit 2
fi

ashare_universe_count() {
  local dsn="$1"
  "${PYTHON_RUN[@]}" - "$dsn" 2>/dev/null <<'PY' || echo 0
import sys
import psycopg

dsn = sys.argv[1]
with psycopg.connect(dsn) as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT payload->>'ticker')
            FROM ai_quant.records
            WHERE collection = 'securities'
              AND payload->>'market' = 'A'
              AND COALESCE(payload->>'status', 'active') = 'active'
              AND payload->>'company_universe_scope' = 'in_scope'
            """
        )
        print(int(cursor.fetchone()[0] or 0))
PY
}

us_universe_count() {
  local dsn="$1"
  "${PYTHON_RUN[@]}" - "$dsn" 2>/dev/null <<'PY' || echo 0
import sys
import psycopg

dsn = sys.argv[1]
with psycopg.connect(dsn) as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT upper(payload->>'ticker'))
            FROM ai_quant.records
            WHERE collection = 'securities'
              AND payload->>'market' = 'U'
              AND COALESCE(payload->>'status', 'active') = 'active'
              AND COALESCE(payload->>'market_data_refresh_scope', 'in_scope') = 'in_scope'
              AND COALESCE(payload->>'ticker', '') <> ''
            """
        )
        print(int(cursor.fetchone()[0] or 0))
PY
}

state_offset() {
  local file="$1"
  local batch_size="$2"
  local universe_count="$3"
  local state_key="$4"
  local target_key="$5"
  local target_date="$6"
  python3 - "$file" "$batch_size" "$universe_count" "$state_key" "$target_key" "$target_date" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
batch_size = max(1, int(sys.argv[2] or 1))
universe_count = max(0, int(sys.argv[3] or 0))
state_key = sys.argv[4]
target_key = sys.argv[5]
target_date = sys.argv[6]
state = {}
if path.exists():
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        state = {}
offset = int(state.get(state_key) or 0)
if target_date and state.get(target_key) != target_date:
    offset = 0
if universe_count > 0 and offset >= universe_count:
    offset = 0
print(max(0, offset))
PY
}

market_target_date() {
  local market="$1"
  python3 - "$market" "$RUN_DATE" "$END_DATE" <<'PY'
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

market, run_date, forced_end_date = sys.argv[1:4]
if forced_end_date:
    print(forced_end_date)
    raise SystemExit(0)

def latest_ready_weekday(tz_name: str, ready_hour: int, ready_minute: int = 0) -> str:
    now = datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(tz_name))
    candidate = local.date()
    if candidate.weekday() >= 5 or local.time() < time(ready_hour, ready_minute):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.isoformat()

if market in {"A", "TDX"}:
    print(latest_ready_weekday("Asia/Shanghai", 18, 0))
elif market == "U":
    print(latest_ready_weekday("America/New_York", 18, 0))
else:
    print(run_date)
PY
}

ASHARE_TARGET_DATE="$(market_target_date A)"
US_TARGET_DATE="$(market_target_date U)"

UNIVERSE_COUNT=0
if bool_enabled "$RUN_ASHARE_INCREMENTAL" && ! bool_enabled "$SKIP_ASHARE"; then
  UNIVERSE_COUNT="$(ashare_universe_count "$PIPELINE_DSN")"
  if [ -z "$ASHARE_OFFSET" ]; then
    ASHARE_OFFSET="$(state_offset "$STATE_FILE" "$ASHARE_BATCH_SIZE" "$UNIVERSE_COUNT" "next_ashare_offset" "last_ashare_target_date" "$ASHARE_TARGET_DATE")"
  fi
else
  ASHARE_OFFSET=0
fi

US_UNIVERSE_COUNT=0
if bool_enabled "$RUN_US_INCREMENTAL_FROM_DB" && ! bool_enabled "$SKIP_US"; then
  US_UNIVERSE_COUNT="$(us_universe_count "$PIPELINE_DSN")"
  if [ -z "$US_OFFSET" ]; then
    US_OFFSET="$(state_offset "$STATE_FILE" "$US_BATCH_SIZE" "$US_UNIVERSE_COUNT" "next_us_offset" "last_us_target_date" "$US_TARGET_DATE")"
  fi
else
  US_OFFSET=0
fi

PIPELINE_OUTPUT="${OUTPUT_DIR%/}/daily-update-${RUN_DATE}.json"
PIPELINE_ARGS=(
  "scripts/daily_data_update_pipeline.py"
  "--dsn" "$PIPELINE_DSN"
  "--base-url" "$PIPELINE_BASE_URL"
  "--run-date" "$RUN_DATE"
  "--output-dir" "$OUTPUT_DIR"
  "--output" "$PIPELINE_OUTPUT"
  "--vipdoc-path" "$PIPELINE_VIPDOC_PATH"
  "--api-timeout-seconds" "${AI_QUANT_DAILY_API_TIMEOUT_SECONDS:-60}"
  "--latency-threshold-ms" "${AI_QUANT_DAILY_LATENCY_THRESHOLD_MS:-7000}"
  "--audit-timeout-seconds" "${AI_QUANT_DAILY_AUDIT_TIMEOUT_SECONDS:-900}"
  "--analysis-timeout-seconds" "${AI_QUANT_DAILY_ANALYSIS_TIMEOUT_SECONDS:-1800}"
  "--latest-analysis-semantic-timeout-seconds" "${AI_QUANT_DAILY_LATEST_ANALYSIS_SEMANTIC_TIMEOUT_SECONDS:-8}"
  "--import-timeout-seconds" "${AI_QUANT_DAILY_IMPORT_TIMEOUT_SECONDS:-7200}"
  "--us-tickers" "${AI_QUANT_DAILY_US_TICKERS:-AAPL,MSFT,NVDA,TSLA,SPY}"
  "--research-binding-tickers" "${AI_QUANT_DAILY_RESEARCH_BINDING_TICKERS:-AAPL,MSFT,NVDA,TSLA,SPY,300750,600519,000001,600000}"
  "--research-binding-artifact-limit" "${AI_QUANT_DAILY_RESEARCH_BINDING_ARTIFACT_LIMIT:-40}"
  "--min-direct-evidence-companies" "${AI_QUANT_DAILY_MIN_DIRECT_EVIDENCE_COMPANIES:-7}"
)

if [ -n "$END_DATE" ]; then
  PIPELINE_ARGS+=("--end-date" "$END_DATE")
fi

if bool_enabled "$RUN_ASHARE_INCREMENTAL"; then
  PIPELINE_ARGS+=(
    "--run-ashare-incremental"
    "--ashare-batch-size" "$ASHARE_BATCH_SIZE"
    "--ashare-offset" "$ASHARE_OFFSET"
  )
fi

if bool_enabled "$RUN_ASHARE_SCOPE_REFRESH"; then
  PIPELINE_ARGS+=("--run-ashare-scope-refresh")
fi

if bool_enabled "$SKIP_ASHARE"; then
  PIPELINE_ARGS+=("--skip-ashare")
fi

if bool_enabled "$RUN_TDX_INCREMENTAL"; then
  PIPELINE_ARGS+=("--tdx-incremental")
fi

if bool_enabled "$SKIP_TDX_COVERAGE_AUDIT"; then
  PIPELINE_ARGS+=("--skip-tdx-coverage-audit")
fi

if bool_enabled "$RUN_US_INCREMENTAL_FROM_DB"; then
  PIPELINE_ARGS+=(
    "--us-tickers-from-db"
    "--us-batch-size" "$US_BATCH_SIZE"
    "--us-offset" "$US_OFFSET"
  )
fi

if bool_enabled "$RUN_US_SCOPE_REFRESH"; then
  PIPELINE_ARGS+=("--run-us-scope-refresh")
fi

if bool_enabled "$SKIP_US"; then
  PIPELINE_ARGS+=("--skip-us")
fi

if bool_enabled "$ALLOW_IMPORT_FAILURE"; then
  PIPELINE_ARGS+=("--allow-import-failure")
fi

if bool_enabled "$SKIP_RESEARCH_BINDING"; then
  PIPELINE_ARGS+=("--skip-research-binding")
fi

if bool_enabled "$SKIP_LATEST_ANALYSIS"; then
  PIPELINE_ARGS+=("--skip-latest-analysis")
fi

if bool_enabled "$ALLOW_LATEST_ANALYSIS_FAILURE"; then
  PIPELINE_ARGS+=("--allow-latest-analysis-failure")
fi

if bool_enabled "$SKIP_LOCAL_PRODUCTION_AUDIT"; then
  PIPELINE_ARGS+=("--skip-local-production-audit")
fi

if bool_enabled "$RUN_PROJECT_COMPLETION_AUDIT"; then
  PIPELINE_ARGS+=("--run-project-completion-audit")
fi

if bool_enabled "$SKIP_PROJECT_COMPLETION_AUDIT"; then
  PIPELINE_ARGS+=("--skip-project-completion-audit")
fi

set +e
"${PYTHON_RUN[@]}" "${PIPELINE_ARGS[@]}"
PIPELINE_STATUS=$?
set -e

python3 - "$LATEST_POINTER" "$PIPELINE_OUTPUT" "$OUTPUT_DIR" "$RUN_DATE" "$RUN_ID" "$PIPELINE_STATUS" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "run_date": sys.argv[4],
    "run_id": sys.argv[5],
    "status_code": int(sys.argv[6]),
    "pipeline_output": sys.argv[2],
    "output_dir": sys.argv[3],
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

if bool_enabled "$RUN_ASHARE_SCOPE_REFRESH" || bool_enabled "$RUN_ASHARE_INCREMENTAL" || bool_enabled "$RUN_US_INCREMENTAL_FROM_DB" || bool_enabled "$RUN_US_SCOPE_REFRESH"; then
  python3 - "$STATE_FILE" "$PIPELINE_OUTPUT" "$OUTPUT_DIR" "$RUN_DATE" "$RUN_ID" "$ASHARE_OFFSET" "$ASHARE_BATCH_SIZE" "$UNIVERSE_COUNT" "$US_OFFSET" "$US_BATCH_SIZE" "$US_UNIVERSE_COUNT" "$PIPELINE_STATUS" "$RUN_ASHARE_INCREMENTAL" "$RUN_US_INCREMENTAL_FROM_DB" "$RUN_ASHARE_SCOPE_REFRESH" "$SKIP_ASHARE" "$SKIP_US" "$RUN_US_SCOPE_REFRESH" "$ASHARE_TARGET_DATE" "$US_TARGET_DATE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

state_path = Path(sys.argv[1])
pipeline_output = Path(sys.argv[2])
output_dir = Path(sys.argv[3])
run_date = sys.argv[4]
run_id = sys.argv[5]
offset = int(sys.argv[6])
batch_size = max(1, int(sys.argv[7]))
universe_count = max(0, int(sys.argv[8]))
us_offset = int(sys.argv[9])
us_batch_size = max(1, int(sys.argv[10]))
us_universe_count = max(0, int(sys.argv[11]))
status_code = int(sys.argv[12])
run_ashare = sys.argv[13].strip().lower() in {"1", "true", "yes", "y", "on"}
run_us = sys.argv[14].strip().lower() in {"1", "true", "yes", "y", "on"}
run_ashare_scope_refresh = sys.argv[15].strip().lower() in {"1", "true", "yes", "y", "on"}
skip_ashare = sys.argv[16].strip().lower() in {"1", "true", "yes", "y", "on"}
skip_us = sys.argv[17].strip().lower() in {"1", "true", "yes", "y", "on"}
run_us_scope_refresh = sys.argv[18].strip().lower() in {"1", "true", "yes", "y", "on"}
ashare_target_date = sys.argv[19]
us_target_date = sys.argv[20]
state = {}
if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        state = {}

ashare_artifact = output_dir / f"ashare-eod-baostock-incremental-{run_date}.json"
advance = False
ashare_status = "not_run"
ashare_symbol_count = 0
ashare_typed_rows = 0
ashare_queried_count = 0
if run_ashare and not skip_ashare and status_code == 0 and ashare_artifact.exists():
    try:
        ashare = json.loads(ashare_artifact.read_text(encoding="utf-8"))
        ashare_status = str(ashare.get("status") or "unknown")
        ashare_symbol_count = int(ashare.get("symbol_count") or 0)
        ashare_typed_rows = int(ashare.get("typed_bar_rows") or ashare.get("created_or_updated_rows") or 0)
        ashare_queried_count = int(ashare.get("queried_symbol_count") or 0)
        advance = ashare_status in {"passed", "partial"} and ashare_symbol_count > 0
    except Exception as exc:
        ashare_status = f"unreadable:{type(exc).__name__}"

if advance:
    next_offset = offset + batch_size
    if universe_count > 0 and next_offset >= universe_count:
        next_offset = 0
    state["next_ashare_offset"] = next_offset
else:
    state["next_ashare_offset"] = offset

us_artifact = output_dir / f"us-eod-yahoo-incremental-{run_date}.json"
us_advance = False
us_status = "not_run"
us_symbol_count = 0
us_typed_rows = 0
if run_us and not skip_us and status_code == 0 and us_artifact.exists():
    try:
        us = json.loads(us_artifact.read_text(encoding="utf-8"))
        us_status = str(us.get("status") or "unknown")
        us_symbol_count = int(us.get("symbol_count") or len(us.get("tickers") or []))
        us_typed_rows = int(us.get("typed_bar_rows") or us.get("created_or_updated_rows") or 0)
        us_advance = us_status in {"passed", "partial"} and us_symbol_count > 0
    except Exception as exc:
        us_status = f"unreadable:{type(exc).__name__}"

if us_advance:
    next_us_offset = us_offset + us_batch_size
    if us_universe_count > 0 and next_us_offset >= us_universe_count:
        next_us_offset = 0
    state["next_us_offset"] = next_us_offset
else:
    state["next_us_offset"] = us_offset

state.update(
    {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_run_date": run_date,
        "last_run_id": run_id,
        "last_pipeline_output": str(pipeline_output),
        "last_pipeline_status_code": status_code,
        "last_ashare_offset": offset,
        "last_ashare_batch_size": batch_size,
        "last_ashare_universe_count": universe_count,
        "last_ashare_artifact": str(ashare_artifact),
        "last_ashare_status": ashare_status,
        "last_ashare_symbol_count": ashare_symbol_count,
        "last_ashare_typed_bar_rows": ashare_typed_rows,
        "last_ashare_queried_symbol_count": ashare_queried_count,
        "last_ashare_target_date": ashare_target_date,
        "last_us_offset": us_offset,
        "last_us_batch_size": us_batch_size,
        "last_us_universe_count": us_universe_count,
        "last_us_artifact": str(us_artifact),
        "last_us_status": us_status,
        "last_us_symbol_count": us_symbol_count,
        "last_us_typed_bar_rows": us_typed_rows,
        "last_us_target_date": us_target_date,
    }
)
try:
    if pipeline_output.exists():
        pipeline = json.loads(pipeline_output.read_text(encoding="utf-8"))
        effective_end_dates = pipeline.get("effective_end_dates")
        if isinstance(effective_end_dates, dict):
            state["last_effective_end_dates"] = effective_end_dates
            state["last_ashare_target_date"] = str(effective_end_dates.get("A") or ashare_target_date)
            state["last_us_target_date"] = str(effective_end_dates.get("U") or us_target_date)
except Exception as exc:
    state["last_pipeline_state_warning"] = f"effective_end_dates_unreadable:{type(exc).__name__}"
if run_ashare_scope_refresh and not skip_ashare:
    state["last_ashare_scope_refresh"] = True
if run_us and not skip_us:
    state["last_us_tickers_from_db"] = True
if run_us_scope_refresh and not skip_us:
    state["last_us_scope_refresh"] = True
state_path.parent.mkdir(parents=True, exist_ok=True)
tmp = state_path.with_suffix(state_path.suffix + ".tmp")
tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
tmp.replace(state_path)
PY
fi

exit "$PIPELINE_STATUS"
