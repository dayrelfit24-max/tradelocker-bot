#!/usr/bin/env python3
"""
Fetch TradeLocker closed trades via ordersHistory endpoint.
Groups by positionId — uses TradeLocker's own position matching (not manual FIFO).
Credentials are read from ~/tradelocker-bot/config.env — never hardcoded.
"""
import csv, json, requests, hashlib
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# ── Config ─────────────────────────────────────────────────────────────────
CONFIG  = Path.home() / "tradelocker-bot" / "config.env"
OUT     = Path.home() / "tradelocker-bot" / "tradelocker_trades.json"
JOURNAL = Path.home() / "tradelocker-bot" / "trades_journal.csv"
BASE    = "https://live.tradelocker.com/backend-api"

def load_journal_strategy(symbol, action, entry_price):
    """Look up strategy from trades_journal.csv by symbol+action+entry."""
    try:
        if not JOURNAL.exists():
            return "unknown"
        with open(JOURNAL, newline="") as f:
            for row in csv.DictReader(f):
                if (row.get("symbol","").upper() == symbol.upper()
                        and row.get("action","").lower() == action.lower()
                        and abs(float(row.get("entry", 0)) - entry_price) < 0.5):
                    return row.get("strategy", "unknown")
    except Exception:
        pass
    return "unknown"

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

cfg = load_env(CONFIG)
EMAIL    = cfg.get("TL_EMAIL", "")
PASSWORD = cfg.get("TL_PASSWORD", "")
SERVER   = cfg.get("TL_SERVER", "HEROFX")
ACC_ID   = cfg.get("TL_ACCOUNT_ID", "")

if not EMAIL or not PASSWORD:
    print("❌  TL_EMAIL / TL_PASSWORD missing from config.env")
    exit(1)

# ── Auth ────────────────────────────────────────────────────────────────────
print("Connecting to TradeLocker...")
r = requests.post(f"{BASE}/auth/jwt/token", json={
    "email": EMAIL, "password": PASSWORD, "server": SERVER
}, timeout=15)
r.raise_for_status()
data = r.json()

# JWT endpoint returns token directly (no s/d wrapper)
# Try both formats
if "accessToken" in data:
    access_token = data["accessToken"]
elif data.get("s") == "ok" and "d" in data:
    access_token = data["d"]["accessToken"]
else:
    print(f"❌  Auth failed: {data}")
    exit(1)
h = {"Authorization": f"Bearer {access_token}"}
print("  Connected!")

# ── Get account list (need accNum for /trade/ headers) ──────────────────────
accounts_resp = requests.get(f"{BASE}/auth/jwt/all-accounts", headers=h, timeout=15)
accounts_data = accounts_resp.json()

# Response can be {"accounts": [...]} or {"d": {"accounts": [...]}}
accounts = (accounts_data.get("accounts")
            or accounts_data.get("d", {}).get("accounts", []))

if not accounts:
    print(f"❌  No accounts found: {accounts_data}")
    exit(1)

print(f"  Found {len(accounts)} account(s)")

# Pick account matching TL_ACCOUNT_ID, or the one with highest balance, or first
acc_num = 1
acc_id  = ACC_ID

best = None
for acc in accounts:
    aid = str(acc.get("id", ""))
    if ACC_ID and aid == str(ACC_ID):
        best = acc
        break
    # prefer account with positive balance
    bal = float(acc.get("accountBalance", 0) or 0)
    if best is None or bal > float(best.get("accountBalance", 0) or 0):
        best = acc

if best:
    acc_id  = str(best.get("id", acc_id))
    acc_num = int(best.get("accNum", 1))

print(f"  Account: {acc_id}  (accNum={acc_num})")
trade_headers = {**h, "accNum": str(acc_num)}

# ── Get config to learn ordersHistory column names ──────────────────────────
config_resp = requests.get(f"{BASE}/trade/config", headers=trade_headers, timeout=15)
config_data = config_resp.json().get("d", {})
oh_cols = config_data.get("ordersHistoryConfig", {}).get("columnNames", [])

# Fallback: use column positions from TradeLocker API docs if config returns empty
# From docs example: orderId, accountId, tradableInstrumentId, qty, side, type,
#   status, filledQty, price, averageFillPrice, commission, validity, stopPrice,
#   createdTimestamp, updatedTimestamp, isReducing, positionId, ...
FALLBACK_COLS = [
    "id", "tradableInstrumentId", "brokerId", "qty", "side", "type",
    "status", "filledQty", "price", "averageFillPrice", "commission", "validity",
    "stopPrice", "createdTimestamp", "updatedTimestamp", "isReducing", "positionId",
    "slPrice", "tpPrice", "trailingOffset", "digitalSignature", "userNote"
]
if not oh_cols:
    oh_cols = FALLBACK_COLS
    print(f"  ordersHistory columns: [using API docs defaults]")
else:
    print(f"  ordersHistory columns: {oh_cols}")

def col(row, name):
    """Get value from a row by column name."""
    if isinstance(row, dict):
        return row.get(name)
    try:
        idx = oh_cols.index(name)
        return row[idx] if idx < len(row) else None
    except ValueError:
        return None

# ── Fetch all orders history (paginated) ────────────────────────────────────
all_orders = []
params = {}
while True:
    resp = requests.get(
        f"{BASE}/trade/accounts/{acc_id}/ordersHistory",
        headers=trade_headers, params=params, timeout=30
    )
    body = resp.json()
    if body.get("s") != "ok":
        print(f"❌  ordersHistory error: {body}")
        break
    rows = body.get("d", {}).get("ordersHistory", [])
    all_orders.extend(rows)
    has_more = body.get("d", {}).get("hasMore", False)
    print(f"  Fetched {len(rows)} orders  (hasMore={has_more}  total={len(all_orders)})")
    if not has_more:
        break
    # Advance to next page using last row's timestamp
    if rows and oh_cols:
        last_ts = col(rows[-1], "createdTimestamp") or col(rows[-1], "updatedTimestamp")
        if last_ts:
            params["from"] = int(last_ts) + 1
        else:
            break
    else:
        break

# ── Keep only Filled orders ──────────────────────────────────────────────────
filled = [r for r in all_orders if str(col(r, "status") or "").lower() == "filled"]
print(f"  {len(filled)} filled orders out of {len(all_orders)} total")

# ── Build instrument ID → symbol map ────────────────────────────────────────
# Fetch instruments list once
instr_cache = {}
try:
    instr_resp = requests.get(
        f"{BASE}/trade/accounts/{acc_id}/instruments",
        headers=trade_headers, timeout=30
    )
    instr_body = instr_resp.json()
    instr_data = instr_body.get("d", {})
    instr_cols  = instr_data.get("columnNames", [])
    instr_rows  = instr_data.get("instruments", [])
    def icol(row, name):
        try:
            idx = instr_cols.index(name)
            return row[idx] if idx < len(row) else None
        except ValueError:
            return None
    for row in instr_rows:
        tid  = str(icol(row, "tradableInstrumentId") or "")
        name = str(icol(row, "name") or icol(row, "description") or tid)
        if tid:
            instr_cache[tid] = name
    print(f"  {len(instr_cache)} instruments loaded")
except Exception as e:
    print(f"  ⚠ Could not load instruments: {e}")

# Hardcoded fallback for known instrument IDs
# (both instrumentId and tradableInstrumentId variants)
KNOWN = {
    "3883": "US30",
    "3884": "NAS100",
    "3366": "XAUUSD",
    "3389": "ETHUSD",   # was incorrectly "XAUUSD" — 3389 is Ethereum
    "3378": "BTCUSD",
    "3470": "EURUSD",
    "509994": "US30",
    "4327108": "M6A1",
}
for k, v in KNOWN.items():
    instr_cache.setdefault(k, v)

# Debug: print instruments endpoint response for future mapping
try:
    sample_ids = list({str(col(r, "tradableInstrumentId")) for r in filled[:20]})
    unknown = [x for x in sample_ids if x not in instr_cache]
    if unknown:
        print(f"  ⚠ Unknown tradableInstrumentIds in sample: {unknown}")
        # Try fetching each unknown one
        for uid in unknown[:5]:
            try:
                det = requests.get(f"{BASE}/trade/instruments/{uid}",
                                   headers=trade_headers, timeout=10).json()
                name = (det.get("d", {}) or det).get("name", "")
                if name:
                    print(f"    {uid} → {name}")
                    instr_cache[uid] = name
            except Exception:
                pass
except Exception as e:
    print(f"  Debug lookup skipped: {e}")

def detect_symbol_by_price(price):
    """Fallback: infer symbol from price level when instrument ID is unknown."""
    try:
        p = float(price)
    except Exception:
        return None
    if 1500 <= p <= 5500:
        return "XAUUSD"
    if 14000 <= p <= 38000:
        return "NAS100"
    if 38000 <= p <= 70000:
        return "US30"
    if p > 70000:
        return "BTCUSD"
    return None

def get_symbol(tradable_id, price_hint=None):
    tid = str(tradable_id or "")
    name = instr_cache.get(tid)
    if name:
        return name
    # Unknown instrument ID — try price-range detection
    if price_hint is not None:
        detected = detect_symbol_by_price(price_hint)
        if detected:
            instr_cache[tid] = detected  # cache for this run
            return detected
    return f"INSTR_{tid}"

# ── P&L multipliers (USD per 1 lot per 1 point) ──────────────────────────────
# XAUUSD: 1 lot = 100 oz, each $1/oz move = $100 profit per lot
# EURUSD: 1 lot = 100,000 units; price moves in 0.0001 increments = $10/pip/lot
# ETHUSD: 1 lot = 1 ETH; price in USD, no extra multiplier needed
MULTIPLIERS = {
    "US30":   1.0,
    "NAS100": 1.0,
    "XAUUSD": 100.0,
    "BTCUSD": 1.0,
    "ETHUSD": 1.0,
    "EURUSD": 100000.0,
    "M6A1":   1.0,
    "M6E":    1.0,
}

def get_mult(symbol):
    for prefix, mult in MULTIPLIERS.items():
        if symbol.upper().startswith(prefix):
            return mult
    return 1.0

# ── Group filled orders by positionId ───────────────────────────────────────
by_position = defaultdict(list)
for row in filled:
    pos_id = col(row, "positionId")
    if pos_id:
        by_position[str(pos_id)].append(row)

print(f"  {len(by_position)} unique positions")

# ── Build round-trip trades from positionId groups ──────────────────────────
def parse_ts(ts_ms):
    """Convert ms timestamp to ISO string."""
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return str(ts_ms)

def stable_id(symbol, direction, entry, exit_px, date_str):
    key = f"{symbol}_{direction}_{entry}_{exit_px}_{str(date_str)[:16]}"
    return "tl_" + hashlib.md5(key.encode()).hexdigest()[:12]

new_trades = []
for pos_id, orders in by_position.items():
    # Sort by timestamp
    def get_ts(r):
        ts = col(r, "createdTimestamp") or col(r, "updatedTimestamp") or "0"
        try: return int(ts)
        except: return 0
    orders.sort(key=get_ts)

    def avg_price(row):
        p = col(row, "averageFillPrice") or col(row, "filledPrice") or col(row, "price")
        try: return float(p)
        except: return 0.0

    def filled_qty(row):
        q = col(row, "filledQty") or col(row, "qty")
        try: return float(q)
        except: return 0.0

    def is_reducing(r):
        v = col(r, "isReducing")
        if v is None:
            return False
        return str(v).lower() in ("true", "1", "yes")

    # Split by isReducing first (most reliable)
    openers = [o for o in orders if not is_reducing(o)]
    closers = [o for o in orders if is_reducing(o)]

    # Fallback to buy/sell pairing when isReducing not set
    if not openers or not closers:
        buys  = [o for o in orders if str(col(o, "side") or "").lower() == "buy"]
        sells = [o for o in orders if str(col(o, "side") or "").lower() == "sell"]
        if not buys or not sells:
            continue  # open or one-sided
        first_side = str(col(orders[0], "side") or "").lower()
        if first_side == "buy":
            openers, closers = buys, sells
        else:
            openers, closers = sells, buys

    # Use tradableInstrumentId from first order
    tid        = col(orders[0], "tradableInstrumentId")
    price_hint = avg_price(orders[0])
    symbol = get_symbol(tid, price_hint)
    mult   = get_mult(symbol)

    first_side = str(col(openers[0], "side") or "").lower()
    direction  = "Long" if first_side == "buy" else "Short"

    # Weighted-average entry across ALL opening orders
    total_open_qty = sum(filled_qty(o) for o in openers)
    if total_open_qty == 0:
        continue
    entry_price = sum(avg_price(o) * filled_qty(o) for o in openers) / total_open_qty
    open_ts     = parse_ts(get_ts(openers[0]))

    # One trade record per closing order (handles partial closes correctly)
    for closer in closers:
        exit_price = avg_price(closer)
        qty        = filled_qty(closer)
        close_ts   = parse_ts(get_ts(closer))
        if qty == 0 or exit_price == 0:
            continue

        if direction == "Long":
            pnl = round((exit_price - entry_price) * qty * mult, 2)
        else:
            pnl = round((entry_price - exit_price) * qty * mult, 2)

        # Unique ID: positionId + closer orderId so partial closes each get their own record
        closer_order_id = col(closer, "id") or col(closer, "orderId") or exit_price
        trade_id = "tl_" + hashlib.md5(
            f"{pos_id}_{closer_order_id}".encode()
        ).hexdigest()[:12]

        # Pull SL price from the opening order (slPrice column)
        sl_price = None
        for opener in openers:
            v = col(opener, "slPrice")
            if v:
                try: sl_price = round(float(v), 5)
                except: pass
                break

        new_trades.append({
            "id":         trade_id,
            "positionId": pos_id,
            "broker":     "TradeLocker",
            "symbol":     symbol,
            "direction":  direction,
            "entry":      round(entry_price, 5),
            "exit":       exit_price,
            "sl":         sl_price,
            "size":       qty,
            "pnl":        pnl,
            "date":       open_ts,
            "exitTime":   close_ts,
            "strategy":   load_journal_strategy(symbol, "buy" if direction == "Long" else "sell", entry_price),
            "source":     "api",
        })

print(f"  {len(new_trades)} round-trip trades built")

# ── Merge with existing (never erase old data) ──────────────────────────────
existing = []
if OUT.exists():
    try:
        existing = json.loads(OUT.read_text())
        print(f"  {len(existing)} existing trades loaded")
    except Exception:
        pass

# Fix any existing trades labeled INSTR_xxx or wrongly as US30 at non-US30 prices
def fix_symbol(t):
    sym = t.get("symbol", "")
    if sym.startswith("INSTR_") or (sym == "US30" and t.get("entry")):
        detected = detect_symbol_by_price(t["entry"])
        if detected and detected != sym:
            t["symbol"] = detected
    return t

relabeled = 0
for t in existing:
    old = t.get("symbol","")
    fix_symbol(t)
    if t.get("symbol") != old:
        relabeled += 1
if relabeled:
    print(f"  ↻  Relabeled {relabeled} existing trades with correct symbols")

# Deduplicate by trade id (positionId+closerOrderId hash).
# This allows multiple records per positionId for partial closes.
# Also updates P&L and symbol on existing records that had wrong values.
existing_ids = {t.get("id"): i for i, t in enumerate(existing) if t.get("id")}
added = 0
updated = 0

for t in new_trades:
    tid = t.get("id")
    if tid and tid in existing_ids:
        idx = existing_ids[tid]
        changed = False
        # Fix wrong symbol
        if existing[idx].get("symbol","").startswith("INSTR_") or \
           (existing[idx].get("symbol") == "US30" and t.get("symbol") != "US30"):
            existing[idx]["symbol"] = t["symbol"]
            changed = True
        # Fix wrong P&L (e.g. XAUUSD was 100x off)
        if abs(float(existing[idx].get("pnl", 0)) - t["pnl"]) > 0.05:
            existing[idx]["pnl"]   = t["pnl"]
            existing[idx]["entry"] = t["entry"]
            existing[idx]["exit"]  = t["exit"]
            existing[idx]["size"]  = t["size"]
            changed = True
        if changed:
            updated += 1
        continue
    existing.append(t)
    existing_ids[tid] = len(existing) - 1
    added += 1

if updated:
    print(f"  ↻  Updated P&L/symbol on {updated} existing trades")

existing.sort(key=lambda t: t.get("date", ""), reverse=True)
OUT.write_text(json.dumps(existing, indent=2))

from collections import Counter
syms = Counter(t.get("symbol") for t in existing)
wins  = sum(1 for t in existing if float(t.get("pnl",0)) > 0)
loss  = sum(1 for t in existing if float(t.get("pnl",0)) < 0)
total = sum(float(t.get("pnl",0)) for t in existing)

print(f"\n✅  {added} new trades added → {len(existing)} total")
print(f"   W:{wins}  L:{loss}  Total P&L: ${total:,.2f}")
print(f"   Symbols: {dict(syms.most_common())}")
