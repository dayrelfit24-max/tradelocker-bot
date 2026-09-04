#!/usr/bin/env python3
"""
Tradovate live fill poller — checks for new fills every 30 seconds.
When new fills pair into a completed trade, saves it and rebuilds the journal.
Handles re-auth automatically when the token expires.
"""
import json, time, sys, subprocess, logging
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "--break-system-packages", "-q"])
    import requests

BOT    = Path.home() / "tradelocker-bot"
OUT    = BOT / "tradovate_trades.json"
INJECT = BOT / "inject_trades.py"
LOG_F  = BOT / "tradovate_poller.log"
BASE   = "https://live.tradovateapi.com/v1"
POLL   = 30   # seconds between fill checks
REAUTH = 3300 # re-authenticate every 55 min (token lasts 60 min)

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

TV_USER = cfg.get("TV_USERNAME", cfg.get("TV_USER", ""))
TV_PASS = cfg.get("TV_PASSWORD", cfg.get("TV_PASS", ""))
TV_CID  = int(cfg.get("TV_CID", 0))
TV_SEC  = cfg.get("TV_SECRET", cfg.get("TV_SEC", ""))

# ── Multipliers ────────────────────────────────────────────────────────────────
MULT = {"MES": 5, "MNQ": 2, "M2K": 5, "MGC": 10, "M6A": 10000,
        "M6E": 12500, "ES": 50, "NQ": 20, "GC": 100, "MCL": 100}

def get_mult(sym):
    for k, v in MULT.items():
        if str(sym).upper().startswith(k):
            return v
    return 1

# ── Auth ───────────────────────────────────────────────────────────────────────
_token = None
_headers = {}
_contract_cache = {}

def authenticate():
    global _token, _headers
    r = requests.post(f"{BASE}/auth/accesstokenrequest", json={
        "name": TV_USER, "password": TV_PASS,
        "appId": "JournalSync", "appVersion": "1.0.0",
        "cid": TV_CID, "sec": TV_SEC,
        "deviceId": "tradovate-poller",
    }, timeout=20)
    data = r.json()
    _token = data.get("accessToken")
    if not _token:
        log.error(f"Auth failed: {data.get('errorText', data)}")
        return False
    _headers = {"Authorization": f"Bearer {_token}"}
    log.info("Authenticated with Tradovate")
    return True

def get_symbol(contract_id):
    cid = str(contract_id)
    if cid in _contract_cache:
        return _contract_cache[cid]
    try:
        r = requests.get(f"{BASE}/contract/item", params={"id": cid},
                         headers=_headers, timeout=10)
        name = r.json().get("name", cid)
        _contract_cache[cid] = name
        return name
    except Exception:
        return cid

# ── Fill state ─────────────────────────────────────────────────────────────────
# Track fill IDs we've already processed to detect new ones
_seen_fill_ids = set()

def load_seen_ids():
    """Pre-populate seen IDs from existing trades so we don't reprocess."""
    if OUT.exists():
        try:
            trades = json.loads(OUT.read_text())
            for t in trades:
                tid = t.get("id", "")
                # Extract fill IDs from tv_X_Y format
                if tid.startswith("tv_"):
                    parts = tid.split("_")
                    if len(parts) == 3:
                        _seen_fill_ids.add(parts[1])
                        _seen_fill_ids.add(parts[2])
        except Exception:
            pass
    log.info(f"Pre-loaded {len(_seen_fill_ids)} known fill IDs")

# ── Trade saving ───────────────────────────────────────────────────────────────
def to_iso(ts_str):
    try:
        return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).isoformat()
    except Exception:
        return str(ts_str)

def save_trade(symbol, direction, entry, exit_px, qty, open_ts, close_ts, buy_id, sell_id):
    pnl = round((exit_px - entry) * qty * get_mult(symbol) * (1 if direction == "Long" else -1), 2)
    trade_id = f"tv_{min(str(buy_id), str(sell_id))}_{max(str(buy_id), str(sell_id))}"

    existing = []
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text())
        except Exception:
            pass

    if any(t.get("id") == trade_id for t in existing):
        return False  # already saved

    trade = {
        "id":        trade_id,
        "broker":    "Tradovate",
        "symbol":    symbol,
        "direction": direction,
        "entry":     entry,
        "exit":      exit_px,
        "size":      qty,
        "pnl":       pnl,
        "date":      to_iso(open_ts),
        "exitTime":  to_iso(close_ts),
        "strategy":  "Manual",
        "source":    "api-poll",
    }
    existing.append(trade)
    existing.sort(key=lambda t: t.get("date", ""), reverse=True)
    OUT.write_text(json.dumps(existing, indent=2))

    msg = f"NEW TRADE: {symbol} {direction} {entry}→{exit_px} x{qty} = ${pnl:+.2f}"
    log.info(msg)
    print(msg, flush=True)
    return True

def pair_fills(fills):
    """FIFO pair buys and sells within each contract."""
    by_contract = defaultdict(list)
    for f in fills:
        by_contract[str(f.get("contractId",""))].append(f)

    new_trades = 0
    for cid, cfills in by_contract.items():
        cfills.sort(key=lambda x: x.get("timestamp",""))
        symbol = get_symbol(cid)

        buys  = [[f["qty"], f["price"], f["timestamp"], f["id"]]
                 for f in cfills if f.get("action") == "Buy"]
        sells = [[f["qty"], f["price"], f["timestamp"], f["id"]]
                 for f in cfills if f.get("action") == "Sell"]

        bi, si = 0, 0
        while bi < len(buys) and si < len(sells):
            b, s     = buys[bi], sells[si]
            matched  = min(b[0], s[0])

            if b[2] <= s[2]:
                direction = "Long"
                entry, exit_px = b[1], s[1]
                open_ts, close_ts = b[2], s[2]
                buy_id, sell_id = b[3], s[3]
            else:
                direction = "Short"
                entry, exit_px = s[1], b[1]
                open_ts, close_ts = s[2], b[2]
                buy_id, sell_id = b[3], s[3]

            if save_trade(symbol, direction, entry, exit_px, matched,
                          open_ts, close_ts, buy_id, sell_id):
                new_trades += 1

            b[0] -= matched
            s[0] -= matched
            if b[0] == 0: bi += 1
            if s[0] == 0: si += 1

    return new_trades

# ── Poll loop ──────────────────────────────────────────────────────────────────
def poll():
    try:
        resp  = requests.get(f"{BASE}/fill/list", headers=_headers, timeout=15)
        fills = resp.json()
        if not isinstance(fills, list):
            return 0

        # Find fills we haven't seen before
        new_fills = [f for f in fills if str(f.get("id","")) not in _seen_fill_ids]
        if not new_fills:
            return 0

        log.info(f"{len(new_fills)} new fill(s) detected")
        for f in new_fills:
            _seen_fill_ids.add(str(f.get("id","")))

        # Pair ALL current fills (not just new ones, for correct FIFO)
        n = pair_fills(fills)
        if n > 0:
            # Rebuild journal
            subprocess.Popen([sys.executable, str(INJECT)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return n

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            log.warning("Token expired — re-authenticating")
            authenticate()
        else:
            log.error(f"HTTP error: {e}")
    except Exception as e:
        log.error(f"Poll error: {e}")
    return 0

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Tradovate fill poller starting (every {POLL}s) — log: {LOG_F}", flush=True)
    load_seen_ids()

    if not authenticate():
        log.error("Initial auth failed — exiting")
        sys.exit(1)

    last_auth = time.time()

    while True:
        # Re-authenticate before token expires
        if time.time() - last_auth > REAUTH:
            authenticate()
            last_auth = time.time()

        poll()
        time.sleep(POLL)
