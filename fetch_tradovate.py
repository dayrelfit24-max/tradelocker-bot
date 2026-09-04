#!/usr/bin/env python3
"""
Fetch Tradovate closed trades via REST API.
Credentials read from ~/tradelocker-bot/config.env — never hardcoded.
Uses fill IDs as primary dedup key so NO trades are ever dropped.
"""
import json, requests, sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG = Path.home() / "tradelocker-bot" / "config.env"
OUT    = Path.home() / "tradelocker-bot" / "tradovate_trades.json"
BASE   = "https://live.tradovateapi.com/v1"

def load_env(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

cfg     = load_env(CONFIG)
TV_USER = cfg.get("TV_USERNAME", cfg.get("TV_USER", ""))
TV_PASS = cfg.get("TV_PASSWORD", cfg.get("TV_PASS", ""))
TV_CID  = int(cfg.get("TV_CID", "0"))
TV_SEC  = cfg.get("TV_SECRET", cfg.get("TV_SEC", ""))

if not TV_USER or not TV_PASS:
    print("❌  Missing TV_USERNAME / TV_PASSWORD in config.env — skipping Tradovate sync")
    sys.exit(0)

# ── Contract multipliers ($-per-point per contract) ───────────────────────────
MULTIPLIERS = {
    "MES": 5,    # Micro E-mini S&P 500
    "MNQ": 2,    # Micro Nasdaq-100
    "M2K": 5,    # Micro Russell 2000
    "M6A": 10000,# Micro AUD/USD
    "M6E": 12500,# Micro EUR/USD
    "MGC": 10,   # Micro Gold
    "MCL": 100,  # Micro WTI Crude
    "ES":  50,
    "NQ":  20,
    "GC":  100,
}

def get_multiplier(symbol):
    for prefix, mult in MULTIPLIERS.items():
        if symbol.upper().startswith(prefix):
            return mult
    print(f"  ⚠ Unknown multiplier for {symbol} — defaulting to 1")
    return 1

# ── Auth ──────────────────────────────────────────────────────────────────────
print("Connecting to Tradovate...")
r = requests.post(f"{BASE}/auth/accesstokenrequest", json={
    "name":       TV_USER,
    "password":   TV_PASS,
    "appId":      "JournalSync",
    "appVersion": "1.0.0",
    "cid":        TV_CID,
    "sec":        TV_SEC,
    "deviceId":   "journal-sync-bot",
}, timeout=20)
r.raise_for_status()
data  = r.json()
token = data.get("accessToken")
if not token:
    print(f"❌  Auth failed: {data.get('errorText', data)}")
    sys.exit(1)

h = {"Authorization": f"Bearer {token}"}
print("  Connected!")

# ── Fetch fills (try paginated cashStatement for full history, fall back to fill/list) ──
print("  Fetching fills...")
fills = []

# Try executionReport/list which has better history coverage
for endpoint in ["/cashStatement/list", "/fill/list"]:
    try:
        resp = requests.get(f"{BASE}{endpoint}", headers=h, timeout=30)
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            if endpoint == "/fill/list":
                fills = data
            else:
                # cashStatement mixes types — keep only Trade entries with a price
                fills = [x for x in data if x.get("fillPrice") and x.get("tradeType") == "Trade"]
            print(f"  {len(fills)} entries from {endpoint}")
            if len(fills) >= 6:
                break
    except Exception as e:
        print(f"  {endpoint} failed: {e}")

if not fills:
    print("  No fills found — nothing to do")
    import sys; sys.exit(0)

print(f"  {len(fills)} total fills")

if not fills:
    print("  No fills found — nothing to do")
    sys.exit(0)

# ── Resolve contract ID → symbol name (cached) ────────────────────────────────
contract_cache = {}
def get_symbol(contract_id):
    if contract_id in contract_cache:
        return contract_cache[contract_id]
    try:
        r2   = requests.get(f"{BASE}/contract/item", params={"id": contract_id}, headers=h, timeout=10)
        name = r2.json().get("name", f"CONTRACT_{contract_id}")
    except Exception:
        name = f"CONTRACT_{contract_id}"
    contract_cache[contract_id] = name
    return name

# ── Build set of already-known fill-pair IDs ──────────────────────────────────
# Load existing trades first so we can skip pairs we already have
existing = []
if OUT.exists():
    try:
        existing = json.loads(OUT.read_text())
        print(f"  {len(existing)} existing trades loaded")
    except Exception:
        existing = []

# Index by trade id for fast lookup
existing_ids = {t.get("id") for t in existing if t.get("id")}

# ── Group fills by contractId, sort by time ───────────────────────────────────
by_contract = defaultdict(list)
for f in fills:
    if not isinstance(f, dict) or not f.get("id"):
        continue
    by_contract[f["contractId"]].append(f)

for cid in by_contract:
    by_contract[cid].sort(key=lambda x: x.get("timestamp", ""))

# ── FIFO pairing → round-trip trades ─────────────────────────────────────────
def to_iso(ts):
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.isoformat()
    except Exception:
        return str(ts)

new_trades = []
for contract_id, cfills in by_contract.items():
    symbol = get_symbol(contract_id)
    mult   = get_multiplier(symbol)

    buys  = [f for f in cfills if f.get("action") == "Buy"]
    sells = [f for f in cfills if f.get("action") == "Sell"]

    # Work with mutable copies: [qty_remaining, price, timestamp, fill_id]
    bq = [[f["qty"], f["price"], f["timestamp"], f["id"]] for f in buys]
    sq = [[f["qty"], f["price"], f["timestamp"], f["id"]] for f in sells]

    bi, si = 0, 0
    while bi < len(bq) and si < len(sq):
        b, s  = bq[bi], sq[si]
        matched = min(b[0], s[0])

        if b[2] <= s[2]:          # buy opened first → Long
            direction  = "Long"
            entry, exit_px = b[1], s[1]
            open_ts, close_ts = b[2], s[2]
            open_fill, close_fill = b[3], s[3]
        else:                      # sell opened first → Short
            direction  = "Short"
            entry, exit_px = s[1], b[1]
            open_ts, close_ts = s[2], b[2]
            open_fill, close_fill = s[3], b[3]

        pnl = round((exit_px - entry) * matched * mult * (1 if direction == "Long" else -1), 2)

        # Canonical ID: always smaller_fill_id first so dedup is order-independent
        trade_id = f"tv_{min(open_fill, close_fill)}_{max(open_fill, close_fill)}"
        new_trades.append({
            "id":        trade_id,
            "broker":    "Tradovate",
            "symbol":    symbol,
            "direction": direction,
            "entry":     entry,
            "exit":      exit_px,
            "size":      matched,
            "pnl":       pnl,
            "date":      to_iso(open_ts),
            "exitTime":  to_iso(close_ts),
            "strategy":  "Manual",
            "source":    "api",
        })

        b[0] -= matched
        s[0] -= matched
        if b[0] == 0: bi += 1
        if s[0] == 0: si += 1

print(f"  {len(new_trades)} round-trip trades built from fills")

# ── Merge: add only truly new trades (by fill-pair ID) ────────────────────────
added = 0
for t in new_trades:
    if t["id"] not in existing_ids:
        existing.append(t)
        existing_ids.add(t["id"])
        added += 1

existing.sort(key=lambda t: t.get("date", ""), reverse=True)
OUT.write_text(json.dumps(existing, indent=2))

wins  = sum(1 for t in existing if float(t.get("pnl", 0)) > 0)
losses= sum(1 for t in existing if float(t.get("pnl", 0)) < 0)
total = sum(float(t.get("pnl", 0)) for t in existing)

print(f"\n✅  {added} new trades added → {len(existing)} total in JSON")
print(f"   W:{wins}  L:{losses}  Total P&L: ${total:,.2f}")
