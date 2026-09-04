#!/usr/bin/env python3
"""
Tradovate WebSocket listener — captures fills in real-time.
Runs as a background daemon. When a trade closes (buy+sell pair),
writes it to tradovate_trades.json and rebuilds the journal.

Install: python3 -m pip install websocket-client requests
"""
import json, time, threading, logging, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

try:
    import websocket
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "websocket-client", "requests", "-q"])
    import websocket
    import requests

BOT     = Path.home() / "tradelocker-bot"
OUT     = BOT / "tradovate_trades.json"
FILLS   = BOT / "tradovate_fills_cache.json"
LOG_F   = BOT / "tradovate_ws.log"
INJECT  = BOT / "inject_trades.py"
WS_URL  = "wss://live.tradovateapi.com/v1/websocket"
REST    = "https://live.tradovateapi.com/v1"

logging.basicConfig(
    filename=str(LOG_F),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("tradovate_ws")

# ── Load config ────────────────────────────────────────────────────────────────
cfg = {}
try:
    with open(BOT / "config.env") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
except FileNotFoundError:
    log.error("config.env not found"); sys.exit(1)

TV_USER = cfg.get("TV_USERNAME", cfg.get("TV_USER", ""))
TV_PASS = cfg.get("TV_PASSWORD", cfg.get("TV_PASS", ""))
TV_CID  = int(cfg.get("TV_CID", 0))
TV_SEC  = cfg.get("TV_SECRET", cfg.get("TV_SEC", ""))

if not TV_USER or not TV_PASS:
    log.error("Missing TV_USERNAME/TV_PASSWORD"); sys.exit(1)

# ── Contract multipliers ───────────────────────────────────────────────────────
MULT = {"MES": 5, "MNQ": 2, "M2K": 5, "MGC": 10, "M6A": 10000,
        "M6E": 12500, "ES": 50, "NQ": 20, "GC": 100, "MCL": 100}

def get_mult(sym):
    for k, v in MULT.items():
        if str(sym).upper().startswith(k):
            return v
    return 1

# ── In-memory fill buffer ──────────────────────────────────────────────────────
contract_cache = {}   # contractId → symbol name
open_fills     = defaultdict(list)  # contractId → [fill, ...]
_lock          = threading.Lock()

def load_fills_cache():
    """Load persisted open fills so restarts don't lose partial positions."""
    global open_fills
    if FILLS.exists():
        try:
            data = json.loads(FILLS.read_text())
            with _lock:
                for cid, items in data.items():
                    open_fills[cid].extend(items)
            log.info(f"Loaded {sum(len(v) for v in open_fills.values())} cached fills")
        except Exception as e:
            log.warning(f"Could not load fills cache: {e}")

def save_fills_cache():
    with _lock:
        FILLS.write_text(json.dumps(dict(open_fills), indent=2))

# ── Auth ───────────────────────────────────────────────────────────────────────
_token      = None
_account_id = None

def authenticate():
    global _token, _account_id
    log.info("Authenticating with Tradovate...")
    r = requests.post(f"{REST}/auth/accesstokenrequest", json={
        "name": TV_USER, "password": TV_PASS,
        "appId": "JournalSync", "appVersion": "1.0.0",
        "cid": TV_CID, "sec": TV_SEC,
        "deviceId": "tradovate-ws-listener",
    }, timeout=20)
    data = r.json()
    _token = data.get("accessToken")
    if not _token:
        log.error(f"Auth failed: {data.get('errorText', data)}")
        return False

    # Get account ID
    accs = requests.get(f"{REST}/account/list", headers={"Authorization": f"Bearer {_token}"}, timeout=15).json()
    if isinstance(accs, list) and accs:
        _account_id = accs[0]["id"]
        log.info(f"Account: {_account_id}")

    # Resolve contract names ahead of time
    try:
        contracts = requests.get(f"{REST}/contract/list",
                                 headers={"Authorization": f"Bearer {_token}"},
                                 timeout=20).json()
        if isinstance(contracts, list):
            for c in contracts:
                contract_cache[str(c["id"])] = c.get("name", str(c["id"]))
            log.info(f"Loaded {len(contract_cache)} contracts")
    except Exception as e:
        log.warning(f"Contract preload failed: {e}")

    return True

def get_symbol(contract_id):
    cid = str(contract_id)
    if cid in contract_cache:
        return contract_cache[cid]
    try:
        r = requests.get(f"{REST}/contract/item", params={"id": cid},
                         headers={"Authorization": f"Bearer {_token}"}, timeout=10)
        name = r.json().get("name", cid)
        contract_cache[cid] = name
        return name
    except Exception:
        return cid

# ── Trade saving ───────────────────────────────────────────────────────────────
def to_iso(ts_str):
    try:
        ts_str = str(ts_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        return dt.isoformat()
    except Exception:
        return str(ts_str)

def save_trade(symbol, direction, entry, exit_px, qty, open_ts, close_ts, buy_id, sell_id):
    pnl = round((exit_px - entry) * qty * get_mult(symbol) * (1 if direction == "Long" else -1), 2)
    trade_id = f"tv_{min(buy_id, sell_id)}_{max(buy_id, sell_id)}"

    existing = []
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text())
        except Exception:
            pass

    existing_ids = {t.get("id") for t in existing}
    if trade_id in existing_ids:
        log.info(f"Trade {trade_id} already saved — skipping")
        return

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
        "source":    "websocket",
    }
    existing.append(trade)
    existing.sort(key=lambda t: t.get("date", ""), reverse=True)
    OUT.write_text(json.dumps(existing, indent=2))

    log.info(f"✅ Trade saved: {symbol} {direction} {entry}→{exit_px} x{qty} = ${pnl}")
    print(f"✅ Trade saved: {symbol} {direction} {entry}→{exit_px} x{qty} = ${pnl}", flush=True)

    # Rebuild journal
    try:
        subprocess.Popen([sys.executable, str(INJECT)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log.warning(f"inject_trades failed: {e}")

# ── Fill pairing (FIFO) ────────────────────────────────────────────────────────
def process_fill(fill):
    """Add a fill to the buffer and pair if possible."""
    cid    = str(fill.get("contractId") or fill.get("d", {}).get("contractId", ""))
    action = str(fill.get("action") or "").lower()
    qty    = int(fill.get("qty") or fill.get("lastQty") or 1)
    price  = float(fill.get("price") or fill.get("avgPx") or fill.get("lastPx") or 0)
    ts     = fill.get("timestamp") or fill.get("tradeTime") or datetime.now(timezone.utc).isoformat()
    fid    = fill.get("id") or fill.get("fillId") or id(fill)

    if not cid or not action or not price:
        return

    symbol = get_symbol(cid)

    with _lock:
        open_fills[cid].append({
            "action": action, "qty": qty, "price": price,
            "timestamp": ts, "id": fid
        })
        save_fills_cache()

        buys  = [f for f in open_fills[cid] if f["action"] == "buy"]
        sells = [f for f in open_fills[cid] if f["action"] == "sell"]

        # FIFO pair
        bi, si = 0, 0
        bq = [[f["qty"], f["price"], f["timestamp"], f["id"]] for f in buys]
        sq = [[f["qty"], f["price"], f["timestamp"], f["id"]] for f in sells]

        paired = []
        while bi < len(bq) and si < len(sq):
            b, s   = bq[bi], sq[si]
            matched = min(b[0], s[0])

            if b[2] <= s[2]:   # buy opened first → Long
                direction  = "Long"
                entry, exit_px = b[1], s[1]
                open_ts, close_ts = b[2], s[2]
                buy_id, sell_id = b[3], s[3]
            else:               # sell opened first → Short
                direction  = "Short"
                entry, exit_px = s[1], b[1]
                open_ts, close_ts = s[2], b[2]
                buy_id, sell_id = b[3], s[3]

            paired.append((symbol, direction, entry, exit_px, matched,
                           open_ts, close_ts, buy_id, sell_id))
            b[0] -= matched
            s[0] -= matched
            if b[0] == 0: bi += 1
            if s[0] == 0: si += 1

        # Rebuild remaining fills
        remaining = []
        for i, b in enumerate(bq):
            if i >= bi or b[0] > 0:
                remaining.append({"action": "buy",  "qty": b[0], "price": b[1],
                                   "timestamp": b[2], "id": b[3]})
        for i, s in enumerate(sq):
            if i >= si or s[0] > 0:
                remaining.append({"action": "sell", "qty": s[0], "price": s[1],
                                   "timestamp": s[2], "id": s[3]})
        open_fills[cid] = [r for r in remaining if r["qty"] > 0]
        save_fills_cache()

    for trade_args in paired:
        save_trade(*trade_args)

# ── WebSocket handler ──────────────────────────────────────────────────────────
_msg_id = 0

def next_id():
    global _msg_id
    _msg_id += 1
    return _msg_id

def on_open(ws):
    log.info("WebSocket connected")
    print("WebSocket connected", flush=True)
    # Tradovate WS protocol: "endpoint\nid\n\nbody"
    ws.send(f"authorize\n{next_id()}\n\n{json.dumps({'token': _token})}")

def on_message(ws, raw):
    if not raw or raw == "o":
        return  # heartbeat / open frame
    if raw.startswith("h"):
        return  # heartbeat

    # Tradovate frames: "a[JSON]" or just JSON
    if raw.startswith("a"):
        try:
            msgs = json.loads(raw[1:])
        except Exception:
            return
    else:
        try:
            msgs = [json.loads(raw)]
        except Exception:
            return

    for msg in msgs:
        if not isinstance(msg, dict):
            continue

        etype = msg.get("e")
        data  = msg.get("d", {})

        if etype == "authorized":
            log.info("Authorized on WS — subscribing to account updates")
            # Subscribe to account fills
            ws.send(f"user/syncrequest\n{next_id()}\n\n"
                    f"{json.dumps({'accounts': [_account_id]})}")

        elif etype in ("fill", "fills"):
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    log.info(f"Fill received: {item}")
                    process_fill(item)

        elif etype == "props":
            # Real-time property updates — look for fill events
            for prop in (data if isinstance(data, list) else [data]):
                if isinstance(prop, dict) and prop.get("entityType") == "fill":
                    log.info(f"Fill prop: {prop.get('entity', prop)}")
                    entity = prop.get("entity", prop)
                    process_fill(entity)

def on_error(ws, error):
    log.error(f"WS error: {error}")

def on_close(ws, code, msg):
    log.warning(f"WS closed: {code} {msg}")

# ── Heartbeat (Tradovate requires [] ping every 2.5s) ─────────────────────────
def heartbeat_loop(ws):
    while True:
        time.sleep(2.5)
        try:
            ws.send("[]")
        except Exception:
            break

# ── Main reconnect loop ────────────────────────────────────────────────────────
def run():
    load_fills_cache()
    backoff = 5

    while True:
        if not authenticate():
            log.error("Auth failed — retrying in 60s")
            time.sleep(60)
            continue

        log.info(f"Connecting to {WS_URL}")
        ws = websocket.WebSocketApp(
            WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        hb_thread = threading.Thread(target=heartbeat_loop, args=(ws,), daemon=True)
        hb_thread.start()

        ws.run_forever(ping_interval=30, ping_timeout=10)
        log.warning(f"Disconnected — reconnecting in {backoff}s")
        time.sleep(backoff)
        backoff = min(backoff * 2, 120)  # exponential backoff, max 2 min

if __name__ == "__main__":
    print(f"Tradovate WebSocket listener starting — logs: {LOG_F}", flush=True)
    run()
