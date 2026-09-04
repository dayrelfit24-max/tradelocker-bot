#!/usr/bin/env bash
# Install / uninstall ProGamer daily LaunchAgents (macOS)
# Long video 8:00 AM | Short 6:00 PM
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LONG_LABEL="com.progamer.daily.long"
SHORT_LABEL="com.progamer.daily.short"
OLD_LABEL="com.progamer.daily"

chmod +x "$ROOT/run_daily.sh"

_install_one() {
  local src="$1" label="$2"
  local dst="$AGENTS_DIR/$(basename "$src")"
  cp "$src" "$dst"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || launchctl unload "$dst" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dst"
  launchctl enable "gui/$(id -u)/$label"
}

_uninstall_one() {
  local label="$1" name="$2"
  local dst="$AGENTS_DIR/$name"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || launchctl unload "$dst" 2>/dev/null || true
  rm -f "$dst"
}

_growth_test_active() {
  "$ROOT/.venv/bin/python" -c "from growth_test import is_active; raise SystemExit(0 if is_active() else 1)" 2>/dev/null
}

case "${1:-install}" in
  install|growth-test)
    # Remove legacy single-job scheduler if present
    launchctl bootout "gui/$(id -u)/$OLD_LABEL" 2>/dev/null || true
    rm -f "$AGENTS_DIR/com.progamer.daily.plist"

    if [[ "${1:-install}" == "growth-test" ]] || _growth_test_active; then
      _uninstall_one "$LONG_LABEL" "com.progamer.daily.long.plist"
      _install_one "$ROOT/com.progamer.daily.short.plist" "$SHORT_LABEL"
      echo "✅ Growth test schedule (Fortnite Shorts Mon–Fri @ 6 PM):"
      echo "   Long job DISABLED until GROWTH_TEST_UNTIL in config.env"
      echo "   6:00 PM — Short only on weekdays ($SHORT_LABEL)"
    else
      _install_one "$ROOT/com.progamer.daily.long.plist" "$LONG_LABEL"
      _install_one "$ROOT/com.progamer.daily.short.plist" "$SHORT_LABEL"
      echo "✅ Scheduled:"
      echo "   8:00 AM — long video  ($LONG_LABEL)"
      echo "   6:00 PM — Short only  ($SHORT_LABEL)"
    fi
    echo "   Mac must be awake at run time; keep plugged in for renders"
    echo "   Logs: $ROOT/generated/schedule_short_*.log"
    echo ""
    echo "Commands:"
    echo "   $ROOT/install_schedule.sh status"
    echo "   $ROOT/install_schedule.sh test-short"
    echo "   $ROOT/install_schedule.sh uninstall"
    ;;
  uninstall)
    _uninstall_one "$LONG_LABEL" "com.progamer.daily.long.plist"
    _uninstall_one "$SHORT_LABEL" "com.progamer.daily.short.plist"
    launchctl bootout "gui/$(id -u)/$OLD_LABEL" 2>/dev/null || true
    rm -f "$AGENTS_DIR/com.progamer.daily.plist"
    echo "✅ Removed daily schedule"
    ;;
  test-long)
    echo "▶ Running LONG pipeline now (same as 8 AM)..."
    bash "$ROOT/run_daily.sh" long
    echo "✅ Done. Check: $ROOT/generated/schedule_long_*.log"
    ;;
  test-short)
    echo "▶ Running SHORT pipeline now (same as 6 PM)..."
    bash "$ROOT/run_daily.sh" short
    echo "✅ Done. Check: $ROOT/generated/schedule_short_*.log"
    ;;
  status)
    launchctl print "gui/$(id -u)/$LONG_LABEL" 2>/dev/null || echo "Long job: not loaded"
    echo ""
    launchctl print "gui/$(id -u)/$SHORT_LABEL" 2>/dev/null || echo "Short job: not loaded"
    ;;
  *)
    echo "Usage: $0 [install|growth-test|uninstall|test-long|test-short|status]"
    exit 1
    ;;
esac