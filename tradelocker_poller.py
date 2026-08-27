#!/usr/bin/env python3
"""
TradeLocker live poller — detects closed trades within 60 seconds.
Strategy:
  - Every 60s: fetch /positions (open trades) + /ordersHistory?from=<last_ts>
  - ordersHistory is queried with a timestamp cursor so only NEW orders come back
    (avoids fetching all 5456 orders and the 429 rate limit)
  - When new filled order pairs appear → save trade + rebuild journal
"""
import csv, json, time, sys, subprocess, hashlib, logging
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "--break-system-packages", "-q"])
    import requests

BOT      = Path.home() / "tradelocker-bot"
OUT      = BOT / "tradelocker_trades.json"
STATE    = BOT / "tradelocker_poller_state.json"
INJECT   = BOT / "inject_trades.py"
LOG_F    = BOT / "tradelocker_poller.log"
JOURNAL  = BOT / "trades_journal.csv"
BASE     = "https://live.tradelocker.com/backend-api"
POLL     = 60    # seconds between checks
REAUTH   = 3300  # re-auth every 55 min

RAILWAY_URL    = "https://web-production-c41f5.up.railway.app"
RAILWAY_SECRET = "tradelocker_dayrel_2026"

_journal_rows  = None  # cached per run

def _load_journal_rows():
    global _journal_rows
    if _journal_rows is not None:
        return _journal_rows
    rows = []
    if JOURNAL.exists():
        try:
            with open(JOURNAL, newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception:
            pass
    if not rows:
        try:
            import urllib.request
            url = f"{RAILWAY_URL}/journal/csv?secret={RAILWAY_SECRET}"
            with urllib.request.urlopen(url, timeout=10) as r:
                content = r.read().decode()
            rows = list(csv.DictReader(content.splitlines()))
        except Exception:
            pass
    _journal_rows = rows
    return rows

def _refresh_journal_rows():
    """Force re-fetch from Railway on next call (call after each poll cycle)."""
    global _journal_rows
    _journal_rows = None

def load_journal_strategy(symbol, action, entry_price):
    """Return strategy from journal CSV (local or Railway) matching symbol+action+entry."""
    try:
        for row in _load_journal_rows():
            if (row.get("symbol","").upper() == symbol.upper()
                    and row.get("action","").lower() == action.lower()
                    and abs(float(row.get("entry", 0)) - entry_price) < 0.5):
                return row.get("strategy", "unknown")
    except Exception:
        pass
    return "unknown"

logging.basicConfig(
    filename=str(LOG_F), level=logging.INFO,
    format="%(asctime)s %(message)s"
)
log = logging.getLogger()

# ── Config ────────────────────────────────────────────────────────────────────
cfg = {}
with open(BOT / "config.env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()

EMAIL    = cfg.get("TL_EMAIL", "")
PASSWORD = cfg.get("TL_PASSWORD", "")
SERVER   = cfg.get("TL_SERVER", "HEROFX")
ACC_ID   = cfg.get("TL_ACCOUNT_ID", "")

# ── Multipliers / symbol detection ────────────────────────────────────────────
MULT = {"US30": 1.0, "NAS100": 1.0, "XAUUSD": 1.0, "BTCUSD": 1.0, "ETHUSD": 1.0, "EURUSD": 1.0}

def get_mult(sym):
    for k, v in MULT.items():
        if str(sym).upper().startswith(k):
            return v
    return 1.0

def detect_symbol_by_price(price):
    try:
        p = float(price)
        if 1500 <= p <= 5500:   return "XAUUSD"
        if 14000 <= p <= 38000: return "NAS100"
        if 38000 <= p <= 70000: return "US30"
        if p > 70000:           return "BTCUSD"
    except Exception:
        pass
    return None

# ── Auth ───────────────────────────────────────────────────────────────────────
_token   = None
_headers = {}
_th      = {}   # trade headers (with accNum)
_acc_id  = ACC_ID
_acc_num = 1
_instr   = {}   # tradableInstrumentId → symbol name

def authenticate():
    global _token, _headers, _th, _acc_id, _acc_num, _instr
    r = requests.post(f"{BASE}/auth/jwt/token", json={
        "email": EMAIL, "password": PASSWORD, "server": SERVER
    }, timeout=15)
    r.raise_for_status()
    data = r.json()
    _token = data.get("accessToken") or data.get("d", {}).get("accessToken")
    if not _token:
        log.error(f"Auth failed: {data}")
        return False
    _headers = {"Authorization": f"Bearer {_token}"}

    # Get account
    accs_data = requests.get(f"{BASE}/auth/jwt/all-accounts",
                             headers=_headers, timeout=15).json()
    accounts  = accs_data.get("accounts") or accs_data.get("d", {}).get("accounts", [])
    best = max(accounts, key=lambda a: float(a.get("accountBalance", 0) or 0))
    _acc_id  = str(best.get("id", _acc_id))
    _acc_num = int(best.get("accNum", 1))
    _th = {**_headers, "accNum": str(_acc_num)}
    log.info(f"Authenticated — account {_acc_id} accNum={_acc_num}")

    # Load instrument map
    try:
        ir = requests.get(f"{BASE}/trade/accounts/{_acc_id}/instruments",
                          headers=_th, timeout=30).json()
        id_data = ir.get("d", {})
        cols    = id_data.get("columnNames", [])
        rows    = id_data.get("instruments", [])
        def icol(row, name):
            try: return row[cols.index(name)]
            except: return None
        for row in rows:
            tid  = str(icol(row, "tradableInstrumentId") or "")
            name = str(icol(row, "name") or icol(row, "description") or tid)
            if tid: _instr[tid] = name
        log.info(f"Loaded {len(_instr)} instruments")
    except Exception as e:
        log.warning(f"Instrument load failed: {e}")

    return True

def get_symbol(tradable_id, price_hint=None):
    tid  = str(tradable_id or "")
    name = _instr.get(tid)
    if name:
        return name
    if price_hint:
        detected = detect_symbol_by_price(price_hint)
        if detected:
            _instr[tid] = detected
            return detected
    return f"INSTR_{tid}"

# ── State persistence ─────────────────────────────────────────────────────────
def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {}

def save_state(s):
    STATE.write_text(json.dumps(s, indent=2))

# ── Known position IDs (to skip already-saved trades) ────────────────────────
def load_known_pos_ids():
    if OUT.exists():
        try:
            trades = json.loads(OUT.read_text())
            return {t.get("positionId") for t in trades if t.get("positionId")}
        except Exception:
            pass
    return set()

_known_pos_ids = set()

# ── Column helpers ─────────────────────────────────────────────────────────────
# TradeLocker ordersHistory default column order (from API docs)
OH_COLS = [
    "id", "accountId", "tradableInstrumentId", "qty", "side", "type",
    "status", "filledQty", "price", "averageFillPrice", "commission", "validity",
    "stopPrice", "createdTimestamp", "updatedTimestamp", "isReducing", "positionId",
    "slPrice", "tpPrice", "trailingOffset", "digitalSignature", "userNote"
]

def col(row, name, cols=None):
    c = cols or OH_COLS
    if isinstance(row, dict):
        return row.get(name)
    try:
        idx = c.index(name)
        return row[idx] if idx < len(row) else None
    except ValueError:
        return None

def parse_ts(ts_ms):
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return str(ts_ms)

def stable_id(symbol, direction, entry, exit_px, date_str):
    key = f"{symbol}_{direction}_{entry}_{exit_px}_{str(date_str)[:16]}"
    return "tl_" + hashlib.md5(key.encode()).hexdigest()[:12]

# ── Save a new trade ──────────────────────────────────────────────────────────
def save_trade(trade):
    existing = []
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text())
        except Exception:
            pass

    pos_id = trade.get("positionId")
    tid    = trade.get("id")

    # Skip if already saved (by positionId or trade id)
    existing_pos = {t.get("positionId") for t in existing if t.get("positionId")}
    existing_ids = {t.get("id") for t in existing}
    if (pos_id and pos_id in existing_pos) or (tid and tid in existing_ids):
        return False

    existing.append(trade)
    existing.sort(key=lambda t: t.get("date", ""), reverse=True)
    OUT.write_text(json.dumps(existing, indent=2))

    msg = (f"NEW TRADE: {trade['symbol']} {trade['direction']} "
           f"{trade['entry']}→{trade['exit']} x{trade['size']} = ${trade['pnl']:+.2f}")
    log.info(msg)
    print(msg, flush=True)
    return True

# ── Fetch ALL orders for a specific positionId (to find opener) ──────────────
def fetch_orders_for_position(pos_id):
    """Fetch all filled orders for a positionId from full history (no cursor)."""
    try:
        resp = requests.get(
            f"{BASE}/trade/accounts/{_acc_id}/ordersHistory",
            headers=_th, timeout=30
        )
        body = resp.json()
        if body.get("s") != "ok":
            return []
        rows = body.get("d", {}).get("ordersHistory", [])
        return [r for r in rows
                if str(col(r, "positionId")) == str(pos_id)
                and str(col(r, "status") or "").lower() == "filled"]
    except Exception as e:
        log.warning(f"fetch_orders_for_position({pos_id}) error: {e}")
        return []

# ── Fetch only NEW orders (using timestamp cursor) ───────────────────────────
def fetch_new_orders(since_ts_ms):
    """Fetch filled orders newer than since_ts_ms. Returns (orders, newest_ts)."""
    try:
        params = {}
        if since_ts_ms:
            params["from"] = int(since_ts_ms)

        resp = requests.get(
            f"{BASE}/trade/accounts/{_acc_id}/ordersHistory",
            headers=_th, params=params, timeout=30
        )
        if resp.status_code == 429:
            log.warning("Rate limited on ordersHistory — skipping this poll")
            return [], since_ts_ms
        if resp.status_code == 401:
            log.warning("Token expired")
            return None, since_ts_ms  # signal re-auth needed

        body = resp.json()
        if body.get("s") != "ok":
            log.warning(f"ordersHistory error: {body}")
            return [], since_ts_ms

        rows    = body.get("d", {}).get("ordersHistory", [])
        filled  = [r for r in rows if str(col(r, "status") or "").lower() == "filled"]

        # Track newest timestamp for next poll
        newest = since_ts_ms
        for r in rows:
            ts = col(r, "createdTimestamp") or col(r, "updatedTimestamp")
            if ts:
                try:
                    newest = max(newest or 0, int(ts))
                except Exception:
                    pass

        log.info(f"ordersHistory: {len(rows)} orders ({len(filled)} filled) since {since_ts_ms}")
        return filled, newest

    except requests.exceptions.Timeout:
        log.warning("ordersHistory timeout")
        return [], since_ts_ms
    except Exception as e:
        log.error(f"fetch_new_orders error: {e}")
        return [], since_ts_ms

# ── Build trades from filled orders ─────────────────────────────────────────
def build_trades_from_orders(filled):
    by_pos = defaultdict(list)
    for row in filled:
        pos_id = col(row, "positionId")
        if pos_id:
            by_pos[str(pos_id)].append(row)

    new_trades = []
    for pos_id, orders in by_pos.items():
        if pos_id in _known_pos_ids:
            continue

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

        # Split into openers (non-reducing) and closers (reducing)
        openers = [o for o in orders if not is_reducing(o)]
        closers = [o for o in orders if is_reducing(o)]

        # If we only see closers (opener is outside the cursor window), fetch full history
        if not openers and closers:
            all_orders = fetch_orders_for_position(pos_id)
            openers = [o for o in all_orders if not is_reducing(o)]
            closers = [o for o in all_orders if is_reducing(o)]

        # Fallback: if isReducing not set, use buy/sell pairing
        if not openers or not closers:
            buys  = [o for o in orders if str(col(o, "side") or "").lower() == "buy"]
            sells = [o for o in orders if str(col(o, "side") or "").lower() == "sell"]
            if not buys or not sells:
                continue  # position still open
            first_side = str(col(orders[0], "side") or "").lower()
            if first_side == "buy":
                openers, closers = buys, sells
            else:
                openers, closers = sells, buys

        opener = openers[0]
        opener_side = str(col(opener, "side") or "").lower()
        direction   = "Long" if opener_side == "buy" else "Short"

        tid        = col(orders[0], "tradableInstrumentId")
        price_hint = avg_price(orders[0])
        symbol     = get_symbol(tid, price_hint)

        entry_price = avg_price(opener)
        open_ts     = parse_ts(get_ts(opener))

        for closer in closers:
            exit_price = avg_price(closer)
            qty        = min(filled_qty(opener), filled_qty(closer))
            close_ts   = parse_ts(get_ts(closer))

            if direction == "Long":
                pnl = round((exit_price - entry_price) * qty * get_mult(symbol), 2)
            else:
                pnl = round((entry_price - exit_price) * qty * get_mult(symbol), 2)

            new_trades.append({
                "id":         stable_id(symbol, direction, entry_price, exit_price, open_ts),
                "positionId": pos_id,
                "broker":     "TradeLocker",
                "symbol":     symbol,
                "direction":  direction,
                "entry":      entry_price,
                "exit":       exit_price,
                "size":       qty,
                "pnl":        pnl,
                "date":       open_ts,
                "exitTime":   close_ts,
                "strategy":   load_journal_strategy(symbol, "buy" if direction == "Long" else "sell", entry_price),
                "source":     "api-poll",
            })

    return new_trades

# ── Poll open positions (lightweight check) ──────────────────────────────────
_prev_open_pos_ids = set()

def check_positions():
    """Returns True if a position just closed (triggers ordersHistory fetch)."""
    try:
        resp = requests.get(f"{BASE}/trade/accounts/{_acc_id}/positions",
                            headers=_th, timeout=15)
        body = resp.json()
        if body.get("s") != "ok":
            return False

        rows = body.get("d", {}).get("positions", [])
        # Position row[0] is positionId based on what we saw earlier
        current_ids = set()
        for row in rows:
            pid = str(row[0]) if isinstance(row, list) else str(row.get("id",""))
            if pid:
                current_ids.add(pid)

        closed = _prev_open_pos_ids - current_ids
        _prev_open_pos_ids.clear()
        _prev_open_pos_ids.update(current_ids)

        if closed:
            log.info(f"Position(s) just closed: {closed}")
            return True
        return False
    except Exception as e:
        log.warning(f"positions check failed: {e}")
        return False

# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    global _known_pos_ids

    log.info("TradeLocker poller starting")
    print(f"TradeLocker poller starting (every {POLL}s) — log: {LOG_F}", flush=True)

    if not authenticate():
        log.error("Initial auth failed"); sys.exit(1)

    _known_pos_ids = load_known_pos_ids()
    log.info(f"Loaded {len(_known_pos_ids)} known position IDs")

    state      = load_state()
    last_ts    = state.get("last_ts_ms")  # timestamp cursor
    last_auth  = time.time()
    poll_count = 0

    # Initial positions snapshot
    check_positions()

    while True:
        # Re-auth before expiry
        if time.time() - last_auth > REAUTH:
            authenticate()
            last_auth = time.time()

        poll_count += 1
        pos_closed = check_positions()

        # Fetch new orders every poll OR immediately when a position closes
        # Rate limit: ordersHistory at most once per minute
        orders, new_ts = fetch_new_orders(last_ts)

        if orders is None:
            # 401 — re-auth and retry
            authenticate()
            last_auth = time.time()
            orders, new_ts = fetch_new_orders(last_ts)
            if orders is None:
                orders = []

        if new_ts and new_ts != last_ts:
            last_ts = new_ts
            save_state({"last_ts_ms": last_ts, "poll_count": poll_count})

        if orders:
            new_trades = build_trades_from_orders(orders)
            added = 0
            for t in new_trades:
                if save_trade(t):
                    _known_pos_ids.add(t.get("positionId"))
                    added += 1

            if added > 0:
                log.info(f"Saved {added} new TradeLocker trade(s) — rebuilding journal")
                subprocess.Popen([sys.executable, str(INJECT)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        _refresh_journal_rows()  # re-fetch strategy lookup on next cycle
        time.sleep(POLL)

if __name__ == "__main__":
    run()
