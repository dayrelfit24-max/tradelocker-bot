#!/bin/bash
# Trading Journal Auto-Sync
# Runs every 5 minutes via LaunchAgent.
# Logs to ~/tradelocker-bot/sync.log (persistent, survives reboots)

LOG="/Users/dayrelricardo/tradelocker-bot/sync.log"
BOT="/Users/dayrelricardo/tradelocker-bot"

# Find python3 — check common locations
PYTHON=""
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [ -x "$p" ]; then
        PYTHON="$p"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') ERROR: python3 not found" >> "$LOG"
    exit 1
fi

# Rotate log if it gets too big (>500KB)
if [ -f "$LOG" ] && [ $(wc -c < "$LOG") -gt 512000 ]; then
    tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') === Sync started ===" >> "$LOG"

cd "$BOT" || { echo "$(date '+%Y-%m-%d %H:%M:%S') ERROR: cannot cd to $BOT" >> "$LOG"; exit 1; }

# Fetch TradeLocker
"$PYTHON" "$BOT/fetch_tradelocker.py" >> "$LOG" 2>&1
TL_EXIT=$?
if [ $TL_EXIT -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') WARNING: fetch_tradelocker.py exited $TL_EXIT" >> "$LOG"
fi

# Auto-import any Tradovate CSVs dropped in ~/Downloads or ~/tradelocker-bot/
for CSV_FILE in "$HOME/Downloads"/Performance*.csv "$BOT"/Performance*.csv; do
    if [ -f "$CSV_FILE" ]; then
        echo "  Auto-importing CSV: $CSV_FILE" >> "$LOG"
        "$PYTHON" "$BOT/import_tradovate_csv.py" "$CSV_FILE" >> "$LOG" 2>&1
    fi
done

# Fetch Tradovate API (picks up live fills)
"$PYTHON" "$BOT/fetch_tradovate.py" >> "$LOG" 2>&1
TV_EXIT=$?
if [ $TV_EXIT -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') WARNING: fetch_tradovate.py exited $TV_EXIT" >> "$LOG"
fi

# Fetch TakeProfitTrader (Tradovate prop account)
"$PYTHON" "$BOT/fetch_tpt.py" >> "$LOG" 2>&1
TPT_EXIT=$?
if [ $TPT_EXIT -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') WARNING: fetch_tpt.py exited $TPT_EXIT" >> "$LOG"
fi

# Inject into journal HTML
"$PYTHON" "$BOT/inject_trades.py" >> "$LOG" 2>&1
INJ_EXIT=$?
if [ $INJ_EXIT -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') ERROR: inject_trades.py failed (exit $INJ_EXIT)" >> "$LOG"
    exit 1
fi

# Fetch seasonal data from SPY history + regenerate calendar HTML
"$PYTHON" "$BOT/fetch_seasonal.py" >> "$LOG" 2>&1
"$PYTHON" "$BOT/generate_seasonal_html.py" >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') === Sync done ===" >> "$LOG"
