#!/usr/bin/env bash
set -euo pipefail

if [ ! -f "docker-compose.yml" ]; then
  echo "Run this script from the repository root." >&2
  exit 2
fi

ENABLE=false
DRY_RUN=false
UNIT_DIR="${AI_QUANT_DAILY_SYSTEMD_UNIT_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
TIMER_NAME="${AI_QUANT_DAILY_SYSTEMD_TIMER_NAME:-ai-quant-daily-update.timer}"
SERVICE_NAME="${AI_QUANT_DAILY_SYSTEMD_SERVICE_NAME:-ai-quant-daily-update.service}"
ON_CALENDAR="${AI_QUANT_DAILY_SYSTEMD_ON_CALENDAR:-Mon..Fri *-*-* 07:00:00
Mon..Fri *-*-* 18:30:00}"

usage() {
  cat <<'EOF'
Usage: bash scripts/install_daily_update_systemd_user.sh [--enable] [--dry-run] [--unit-dir DIR]

Installs a user-level systemd timer for the local personal-production daily refresh.
The timer calls scripts/run_daily_data_update.sh and keeps K-line writes on the
typed ai_quant.market_data_bars table.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --enable)
      ENABLE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --unit-dir)
      UNIT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(pwd -P)"
RUNNER_SCRIPT="$REPO_ROOT/scripts/run_daily_data_update.sh"
SERVICE_PATH="$UNIT_DIR/$SERVICE_NAME"
TIMER_PATH="$UNIT_DIR/$TIMER_NAME"

SERVICE_CONTENT="[Unit]
Description=AI Quant local personal-production daily data refresh
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
WorkingDirectory=$REPO_ROOT
Environment=AI_QUANT_DAILY_RUNNER=compose
Environment=AI_QUANT_DAILY_REBUILD=false
Environment=AI_QUANT_DAILY_OUTPUT_BASE=artifacts/daily-update-local
Environment=AI_QUANT_DAILY_RUN_ASHARE_SCOPE_REFRESH=true
Environment=AI_QUANT_DAILY_RUN_ASHARE_INCREMENTAL=true
Environment=AI_QUANT_DAILY_ASHARE_BATCH_SIZE=300
Environment=AI_QUANT_DAILY_RUN_US_SCOPE_REFRESH=true
Environment=AI_QUANT_DAILY_US_TICKERS_FROM_DB=true
Environment=AI_QUANT_DAILY_US_BATCH_SIZE=300
Environment=AI_QUANT_DAILY_TDX_INCREMENTAL=false
Environment=AI_QUANT_DAILY_ALLOW_IMPORT_FAILURE=true
Environment=AI_QUANT_DAILY_ALLOW_LATEST_ANALYSIS_FAILURE=false
Environment=AI_QUANT_DAILY_MIN_DIRECT_EVIDENCE_COMPANIES=7
ExecStart=/usr/bin/env bash $RUNNER_SCRIPT
"

TIMER_CONTENT="[Unit]
Description=Run AI Quant local production daily refresh after A-share close

[Timer]
$(printf '%s\n' "$ON_CALENDAR" | sed 's/^/OnCalendar=/')
Persistent=true
RandomizedDelaySec=20min
Unit=$SERVICE_NAME

[Install]
WantedBy=timers.target
"

if [ "$DRY_RUN" = "true" ]; then
  echo "Would write: $SERVICE_PATH"
  printf '%s\n' "$SERVICE_CONTENT"
  echo "Would write: $TIMER_PATH"
  printf '%s\n' "$TIMER_CONTENT"
  exit 0
fi

mkdir -p "$UNIT_DIR"
printf '%s\n' "$SERVICE_CONTENT" > "$SERVICE_PATH"
printf '%s\n' "$TIMER_CONTENT" > "$TIMER_PATH"
chmod 0644 "$SERVICE_PATH" "$TIMER_PATH"

echo "Installed $SERVICE_PATH"
echo "Installed $TIMER_PATH"

if [ "$ENABLE" = "true" ]; then
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl is not available; unit files were installed but timer was not enabled." >&2
    exit 3
  fi
  systemctl --user daemon-reload
  systemctl --user enable --now "$TIMER_NAME"
  systemctl --user list-timers --all "$TIMER_NAME" || true
else
  echo "Timer not enabled. To enable: systemctl --user daemon-reload && systemctl --user enable --now $TIMER_NAME"
fi
