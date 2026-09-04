#!/bin/bash
# Run this ONCE to install the auto-sync.
# After this, the journal syncs every 4 hours automatically — no Terminal needed.

PLIST="$HOME/tradelocker-bot/com.dayrel.tradejournal.plist"
DEST="$HOME/Library/LaunchAgents/com.dayrel.tradejournal.plist"

# Make sync script executable
chmod +x "$HOME/tradelocker-bot/sync_journal.sh"

# Copy plist to LaunchAgents
cp "$PLIST" "$DEST"

# Unload if already installed, then reload
launchctl unload "$DEST" 2>/dev/null
launchctl load "$DEST"

echo ""
echo "✅ Auto-sync installed! Journal will sync every 4 hours automatically."
echo "   Log: ~/tradelocker-bot/sync_journal.log"
echo ""
echo "⚠️  Don't forget to fill in your Tradovate credentials in:"
echo "   ~/tradelocker-bot/config.env"
