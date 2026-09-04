#!/usr/bin/env bash
# ProGamer daily automation — long at 8 AM, Short at 6 PM
# Usage: run_daily.sh [long|short]
set -uo pipefail

ROOT="/Users/dayrelricardo/tradelocker-bot/youtube-pipeline"
PYTHON="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/generated"
SLOT="${1:-long}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$LOG_DIR/schedule_${SLOT}_${STAMP}.log"

mkdir -p "$LOG_DIR"
cd "$ROOT"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

case "$SLOT" in
  long)  PIPE_ARGS="daily --long-only --upload --public" ;;
  short) PIPE_ARGS="daily --short-only --upload --public" ;;
  *)
    echo "Usage: $0 [long|short]"
    exit 1
    ;;
esac

{
  echo "=============================================="
  echo "ProGamer $SLOT run started: $(date)"
  echo "=============================================="

  if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: Python venv not found at $PYTHON"
    exit 1
  fi

  if [[ ! -f "$ROOT/tokens/youtube_token.json" ]]; then
    echo "ERROR: YouTube not authorized. Run: python pipeline.py auth"
    exit 1
  fi

  if ! "$PYTHON" -c "
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import config
creds = Credentials.from_authorized_user_file(str(config.TOKEN_PATH), config.SCOPES)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    config.TOKEN_PATH.write_text(creds.to_json(), encoding='utf-8')
if not creds.valid:
    raise SystemExit(1)
" 2>/dev/null; then
    echo "ERROR: YouTube OAuth expired/revoked — uploads will fail."
    echo "       Fix now: cd $ROOT && $PYTHON pipeline.py auth"
    echo "       Then upload backlog: $PYTHON upload_pending.py"
    exit 1
  fi

  if [[ ! -f "$ROOT/client_secrets.json" ]]; then
    echo "ERROR: Missing client_secrets.json"
    exit 1
  fi

  COOKIES="$ROOT/youtube_cookies.txt"
  if [[ ! -s "$COOKIES" ]]; then
    echo "WARNING: No youtube_cookies.txt — gameplay may use Pexels/Steam only."
    echo "         Run: $ROOT/export_youtube_cookies.sh"
  else
    COOKIE_AGE_DAYS=$(( ( $(date +%s) - $(stat -f %m "$COOKIES") ) / 86400 ))
    if [[ "$COOKIE_AGE_DAYS" -ge 21 ]]; then
      echo "WARNING: youtube_cookies.txt is ${COOKIE_AGE_DAYS} days old — re-export recommended."
    fi
  fi

  "$PYTHON" -m pip install -q -U yt-dlp 2>/dev/null || true

  SKIP_MSG="$("$PYTHON" -c "
from growth_test import should_run_slot, status_line
slot = '$SLOT'
if not should_run_slot(slot):
    print(status_line() or 'growth test skip')
")"
  if [[ -n "$SKIP_MSG" ]]; then
    echo "SKIPPED: $SKIP_MSG"
  else
    caffeinate -i "$PYTHON" pipeline.py $PIPE_ARGS
  fi

  echo "Finished: $(date)"
} >> "$LOG" 2>&1

ls -t "$LOG_DIR"/schedule_"${SLOT}"_*.log 2>/dev/null | tail -n +15 | xargs rm -f 2>/dev/null || true