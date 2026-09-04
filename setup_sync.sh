#!/bin/bash
# Run this ONCE in Terminal to install the journal auto-sync.
# After this, it syncs automatically every 5 minutes.
#
# Usage:  bash ~/tradelocker-bot/setup_sync.sh

set -e

PLIST_SRC="/Users/dayrelricardo/tradelocker-bot/com.dayrel.journal-sync.plist"
PLIST_DST="/Users/dayrelricardo/Library/LaunchAgents/com.dayrel.journal-sync.plist"
SYNC_SH="/Users/dayrelricardo/tradelocker-bot/sync_journal.sh"

echo "=== Trading Journal Sync Setup ==="

# 1. Make scripts executable
chmod +x "$SYNC_SH"
echo "✅  Scripts are executable"

# 2. Unload old agent if loaded
launchctl unload "$PLIST_DST" 2>/dev/null || true

# 3. Copy plist to LaunchAgents
cp "$PLIST_SRC" "$PLIST_DST"
echo "✅  Plist installed to ~/Library/LaunchAgents/"

# 4. Load the agent
launchctl load "$PLIST_DST"
echo "✅  LaunchAgent loaded (syncs every 5 minutes)"

# 5. Run sync immediately right now
echo ""
echo "Running first sync now..."
bash "$SYNC_SH"
echo ""
echo "=== Setup complete! ==="
echo "Your journal at ~/Desktop/trading-journal.html is up to date."
echo "Refresh it in your browser to see the latest trades."
echo ""
echo "Check sync log at: ~/tradelocker-bot/sync.log"
