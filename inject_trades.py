#!/usr/bin/env python3
"""
Merges tradelocker_trades.json + tradovate_trades.json and
embeds trades into trading-journal-template.html → Desktop/trading-journal.html
Uses absolute paths so it works from any working directory (including LaunchAgent).
"""
import json, re, sys, os, fcntl
from pathlib import Path
from datetime import datetime

BOT_DIR  = Path("/Users/dayrelricardo/tradelocker-bot")
DESK     = Path("/Users/dayrelricardo/Desktop")
LOCKFILE = BOT_DIR / ".inject.lock"
TEMPLATE = BOT_DIR / "trading-journal-template.html"
OUTPUT   = DESK    / "trading-journal.html"
TL_JSON  = BOT_DIR / "tradelocker_trades.json"
TV_JSON  = BOT_DIR / "tradovate_trades.json"
TPT_JSON = BOT_DIR / "tpt_trades.json"

# ── Single-instance lock (prevents concurrent runs from corrupting the file) ──
_lock_fh = open(LOCKFILE, "w")
try:
    fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("  [skip] another inject is already running")
    sys.exit(0)

# ── Load trades ───────────────────────────────────────────────────────────────
def load(path, broker_default):
    if not path.exists():
        print(f"  [skip] {path.name} not found")
        return []
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        print(f"  [error] {path.name}: {e}")
        return []
    trades = data if isinstance(data, list) else data.get("trades", [])
    for t in trades:
        t.setdefault("broker", broker_default)
    print(f"  [ok] {path.name}: {len(trades)} trades")
    return trades

tl  = load(TL_JSON,  "TradeLocker")
tv  = load(TV_JSON,  "Tradovate")
all_trades = tl + tv

# De-duplicate by id, then by (positionId, exitTime) — a position can be closed
# in several partial fills, and each of those is a distinct realized trade, so
# positionId alone would collapse them into one.
seen_id, seen_pos, unique = set(), set(), []
for t in all_trades:
    tid = t.get("id") or t.get("orderId") or str(t)
    pos_id = t.get("positionId")
    pos_key = (pos_id, str(t.get("exitTime") or ""), t.get("pnl")) if pos_id else None
    if tid in seen_id:
        continue
    if pos_key and pos_key in seen_pos:
        continue
    seen_id.add(tid)
    if pos_key:
        seen_pos.add(pos_key)
    unique.append(t)

# Bucket every stat by CLOSE date so totals match the broker's own reporting.
# The original open time is preserved as openDate.
reassigned = 0
for t in unique:
    exit_ts = t.get("exitTime")
    if exit_ts:
        if t.get("date") and str(exit_ts)[:10] != str(t["date"])[:10]:
            reassigned += 1
        t["openDate"] = t.get("date")
        t["date"] = exit_ts
if reassigned:
    print(f"  re-bucketed {reassigned} trades to their close date")

# Sort newest first
unique.sort(key=lambda t: t.get("date", ""), reverse=True)
print(f"  total unique trades: {len(unique)}")

# ── Read template ─────────────────────────────────────────────────────────────
if not TEMPLATE.exists():
    print(f"ERROR: template not found at {TEMPLATE}")
    sys.exit(1)

html = TEMPLATE.read_text(encoding="utf-8")

# ── Embed trades ──────────────────────────────────────────────────────────────
trades_js = json.dumps(unique, separators=(',', ':'))  # compact for smaller file
html = re.sub(
    r"const EMBEDDED_TRADES\s*=\s*\[\s*\];",
    f"const EMBEDDED_TRADES = {trades_js};",
    html, count=1
)

# Write to temp file then atomically rename to avoid deadlock when multiple agents run
tmp = OUTPUT.with_suffix(".tmp")
tmp.write_text(html, encoding="utf-8")
os.replace(tmp, OUTPUT)

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
tl_count = len(tl)
tv_count = len(tv)
print(f"  ✅  Saved → {OUTPUT}")
print(f"      TL:{tl_count}  TV:{tv_count}  Total:{len(unique)}  at {now}")
