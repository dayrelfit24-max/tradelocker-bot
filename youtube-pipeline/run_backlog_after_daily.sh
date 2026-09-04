#!/usr/bin/env bash
# Wait for daily batch, then rebuild + upload Jun 11-14 backlog.
set -uo pipefail

ROOT="/Users/dayrelricardo/tradelocker-bot/youtube-pipeline"
PYTHON="$ROOT/.venv/bin/python"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$ROOT/generated/backlog_${STAMP}.log"

cd "$ROOT"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

{
  echo "Waiting for daily batch (PID ${DAILY_PID:-unknown})..."
  if [[ -n "${DAILY_PID:-}" ]]; then
    while kill -0 "$DAILY_PID" 2>/dev/null; do
      sleep 30
    done
  fi
  echo "Starting backlog rebuild: $(date)"
  caffeinate -i "$PYTHON" pipeline.py rebuild-backlog --public
  echo "Backlog finished: $(date)"
} >> "$LOG" 2>&1