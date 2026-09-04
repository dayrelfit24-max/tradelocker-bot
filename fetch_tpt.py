#!/usr/bin/env python3
"""
Fetch TakeProfitTrader (Tradovate prop) closed trades.
Credentials read from ~/tradelocker-bot/config.env
Outputs to tpt_trades.json — logged as broker "TakeProfitTrader"
"""
import json, requests, sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

CONFIG = Path.home() / "tradelocker-bot" / "config.env"
OUT    = Path.home() / "tradelocker-bot" / "tpt_trades.json"
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

cfg      = load_env(CONFIG)
TV_USER  = cfg.get("TPT_USERNAME", "")
TV_PASS  = cfg.get("TPT_PASSWORD", "")
TV_CID   = int(cfg.get("TPT_CID", "0"))
TV_SEC   = cfg.get("TPT_SECRET", "")
TPT_ACCT = cfg.get("TPT_ACCOUNT", "")

if not TV_USER or not TV_PASS:
    print("❌  Missing TPT_USERNAME / TPT_PASSWORD in config.env")
    sys.exit(0)

MULTIPLIERS = {
    "MES": 5, "MNQ": 2, "M2K": 5, "M6A": 10000, "M6E": 12500,
    "MGC": 10, "MCL": 100, "ES": 50, "NQ": 20, "GC": 100,
    "YM": 5, "MYM": 0.5,   # Dow Jones futures
}

def get_multiplier(symbol):
    for prefix, mult in MULTIPLIERS.items():
        if symbol.upper().startswith(prefix):
            return mult
    print(f"  ⚠ Unknown multiplier for {symbol} — defaulting to 1")
    return 1

print("Connecting to TakeProfitTrader (Tradovate)...")
r = requests.post(f"{BASE}/auth/accesstokenrequest", json={
    "name":       TV_USER,
    "password":   TV_PASS,
    "appId":      "JournalSync",
    "appVersion": "1.0.0",
    "cid":        TV_CID,
    "sec":        TV_SEC,
    "deviceId":   "journal-sync-tpt",
}, timeout=20)
r.raise_for_status()
data  = r.json()
token = data.get("accessToken")
if not token:
    print(f"❌  Auth failed: {data.get('errorText', data)}")
    sys.exit(1)

h = {"Authorization": f"Bearer {token}"}
print("  Connected!")

# ── Fetch account ID if needed ───────────────────────────────────────────────
account_id = None
try:
    accts = requests.get(f"{BASE}/account/list", headers=h, timeout=15).json()
    for a in (accts if isinstance(accts, list) else []):
        name = a.get("name", "")
        if TPT_ACCT and TPT_ACCT in name:
            account_id = a.get("id")
            print(f"  Found account: {name} (id={account_id})")
            break
    if not account_id and accts:
        account_id = accts[0].get("id")
        print(f"  Using first account: {accts[0].get('name')} (id={account_id})")
except Exception as e:
    print(f"  ⚠ Could not fetch account list: {e}")

# ── Fetch fills ───────────────────────────────────────────────────────────────
print("  Fetching fills...")
fills = []
for endpoint in ["/fill/list", "/cashStatement/list"]:
    try:
        resp = requests.get(f"{BASE}{endpoint}", headers=h, timeout=30)
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            if endpoint == "/fill/list":
                fills = data
            else:
                fills = [x for x in data if x.get("fillPrice") and x.get("tradeType") == "Trade"]
            print(f"  {len(fills)} entries from {endpoint}")
            if len(fills) >= 1:
                break
    except Exception as e:
        print(f"  {endpoint} failed: {e}")

if not fills:
    print("  No fills found")
    sys.exit(0)

# ── Load existing ─────────────────────────────────────────────────────────────
existing = []
if OUT.exists():
    try:
        existing = json.loads(OUT.read_text())
        print(f"  {len(existing)} existing trades loaded")
    except Exception:
        existing = []
existing_ids = {t.get("id") for t in existing if t.get("id")}

# ── Resolve contract symbols ──────────────────────────────────────────────────
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

def to_iso(ts):
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.isoformat()
    except Exception:
        return str(ts)

# ── FIFO pairing ──────────────────────────────────────────────────────────────
by_contract = defaultdict(list)
for f in fills:
    if isinstance(f, dict) and f.get("id"):
        by_contract[f["contractId"]].append(f)
for cid in by_contract:
    by_contract[cid].sort(key=lambda x: x.get("timestamp", ""))

new_trades = []
for contract_id, cfills in by_contract.items():
    symbol = get_symbol(contract_id)
    mult   = get_multiplier(symbol)
    buys   = [f for f in cfills if f.get("action") == "Buy"]
    sells  = [f for f in cfills if f.get("action") == "Sell"]
    bq = [[f["qty"], f["price"], f["timestamp"], f["id"]] for f in buys]
    sq = [[f["qty"], f["price"], f["timestamp"], f["id"]] for f in sells]
    bi, si = 0, 0
    while bi < len(bq) and si < len(sq):
        b, s     = bq[bi], sq[si]
        matched  = min(b[0], s[0])
        if b[2] <= s[2]:
            direction = "Long"
            entry, exit_px = b[1], s[1]
            open_ts, close_ts = b[2], s[2]
            open_fill, close_fill = b[3], s[3]
        else:
            direction = "Short"
            entry, exit_px = s[1], b[1]
            open_ts, close_ts = s[2], b[2]
            open_fill, close_fill = s[3], b[3]
        pnl = round((exit_px - entry) * matched * mult * (1 if direction == "Long" else -1), 2)
        trade_id = f"tpt_{min(open_fill, close_fill)}_{max(open_fill, close_fill)}"
        new_trades.append({
            "id":        trade_id,
            "broker":    "TakeProfitTrader",
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

print(f"  {len(new_trades)} round-trip trades built")

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

print(f"\n✅  {added} new trades added → {len(existing)} total")
print(f"   W:{wins}  L:{losses}  Total P&L: ${total:,.2f}")

# ── Challenge progress report ─────────────────────────────────────────────────
PROFIT_TARGET  = 1500.0
BALANCE_FLOOR  = 23973.0
START_BALANCE  = 25000.0
MAX_CONTRACTS  = 3

print(f"\n── TakeProfitTrader Challenge Status ──────────────────")
print(f"   Profit target:  ${PROFIT_TARGET:,.2f}")
print(f"   Current P&L:    ${total:,.2f}")
print(f"   Remaining:      ${max(0, PROFIT_TARGET - total):,.2f}")
print(f"   Balance floor:  ${BALANCE_FLOOR:,.2f}")
print(f"   Buffer left:    ${(START_BALANCE + total) - BALANCE_FLOOR:,.2f}")
pct = (total / PROFIT_TARGET * 100) if PROFIT_TARGET else 0
print(f"   Progress:       {pct:.1f}%")
