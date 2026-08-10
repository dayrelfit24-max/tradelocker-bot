#!/usr/bin/env python3
"""
TradeLocker + Tradovate Webhook Bot

Port    : 5002
Endpoints:
  POST /tl/webhook?secret=<WEBHOOK_SECRET>   — TradeLocker (also /nt/webhook)
  POST /tradovate/webhook?secret=<SECRET>    — Tradovate futures
Health  : GET  /health
"""

import os, logging, threading, time
import requests as _requests
from flask import Flask, request, jsonify

# ── Config ─────────────────────────────────────────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
for CONFIG_FILE in [
    os.path.join(_script_dir, "config.env"),
    os.path.expanduser("~/tradelocker-bot/config.env"),
    "/root/tradelocker-bot/config.env",
]:
    if os.path.exists(CONFIG_FILE):
        break

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

cfg = load_env(CONFIG_FILE)

TL_EMAIL        = cfg.get("TL_EMAIL",       os.getenv("TL_EMAIL", ""))
TL_PASSWORD     = cfg.get("TL_PASSWORD",    os.getenv("TL_PASSWORD", ""))
TL_SERVER       = cfg.get("TL_SERVER",      os.getenv("TL_SERVER", "HEROFX"))
ENVIRONMENT     = cfg.get("TL_ENV",         "https://live.tradelocker.com")
RISK_PCT        = float(cfg.get("RISK_PCT",    os.getenv("RISK_PCT",    "1.5")))
POINT_VALUE     = float(cfg.get("POINT_VALUE", os.getenv("POINT_VALUE", "1.0")))
MIN_LOT         = float(cfg.get("MIN_LOT",     os.getenv("MIN_LOT",     "0.01")))
MAX_LOT         = float(cfg.get("MAX_LOT",     os.getenv("MAX_LOT",     "1.0")))
WEBHOOK_SECRET  = cfg.get("WEBHOOK_SECRET", os.getenv("WEBHOOK_SECRET", "tradelocker_dayrel_2026"))

# All TradeLocker account IDs to trade on simultaneously
_acct1 = cfg.get("TL_ACCOUNT_ID",   os.getenv("TL_ACCOUNT_ID",   ""))
_acct2 = cfg.get("TL_ACCOUNT_ID_2", os.getenv("TL_ACCOUNT_ID_2", ""))
TL_ACCOUNT_IDS = [int(a) for a in [_acct1, _acct2] if a.strip()]

# Leverage per account — used to compute margin per lot (entry / leverage)
_lev1 = int(cfg.get("TL_LEVERAGE_1", os.getenv("TL_LEVERAGE_1", "100")))
_lev2 = int(cfg.get("TL_LEVERAGE_2", os.getenv("TL_LEVERAGE_2", "100")))
TL_LEVERAGE_MAP: dict[int, int] = {}
if _acct1.strip(): TL_LEVERAGE_MAP[int(_acct1)] = _lev1
if _acct2.strip(): TL_LEVERAGE_MAP[int(_acct2)] = _lev2

# ── Tradovate config ────────────────────────────────────────────────────────
TV_USER    = cfg.get("TV_USERNAME", os.getenv("TV_USERNAME", ""))
TV_PASS    = cfg.get("TV_PASSWORD", os.getenv("TV_PASSWORD", ""))
TV_CID     = int(cfg.get("TV_CID",  os.getenv("TV_CID", "0")))
TV_SEC     = cfg.get("TV_SECRET",   os.getenv("TV_SECRET", ""))
TV_BASE    = "https://live.tradovateapi.com/v1"

# Contract multipliers: $ per point per 1 contract
# M6E: 12,500 EUR × $1/point = $12,500 per full-point move (price like 1.0850)
# Practical: 1 pip (0.0001) = $1.25 per contract
TV_MULTIPLIERS = {
    "MES": 5,      "ES": 50,
    "MNQ": 2,      "NQ": 20,
    "M2K": 5,      "RTY": 50,
    "MYM": 0.5,    "YM": 5,
    "MGC": 10,     "GC": 100,
    "MCL": 100,    "CL": 1000,
    "MBT": 5,
    "M6E": 12500,  "6E": 125000,   # EUR/USD micro & full
    "M6A": 10000,  "6A": 100000,   # AUD/USD micro & full
    "M6B": 6250,   "6B": 62500,    # GBP/USD micro & full
    "M6J": 1250,   "6J": 12500000, # JPY/USD micro & full (price ~0.0066)
}

def tv_point_value(root: str) -> float:
    for prefix, val in TV_MULTIPLIERS.items():
        if root.upper().startswith(prefix):
            return val
    return 1.0

# ── Logging ────────────────────────────────────────────────────────────────
_log_file = os.path.join(_script_dir, "bot.log")
_file_handler = logging.FileHandler(_log_file)
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(), _file_handler],
)
log = logging.getLogger(__name__)

# ── Tradovate client ───────────────────────────────────────────────────────
_tv_token      = None
_tv_account_id = None
_tv_username   = None
_tv_lock       = threading.Lock()
_tv_token_time = 0.0

def _tv_authenticate():
    global _tv_token, _tv_account_id, _tv_username, _tv_token_time
    r = _requests.post(f"{TV_BASE}/auth/accesstokenrequest", json={
        "name": TV_USER, "password": TV_PASS,
        "appId": "TradeBot", "appVersion": "1.0",
        "cid": TV_CID, "sec": TV_SEC,
        "deviceId": "railway-webhook-bot",
    }, timeout=15)
    r.raise_for_status()
    d = r.json()
    tok = d.get("accessToken")
    if not tok:
        raise RuntimeError(f"Tradovate auth failed: {d.get('errorText', d)}")
    _tv_token      = tok
    _tv_token_time = time.time()
    # Grab account ID
    h = {"Authorization": f"Bearer {tok}"}
    accs = _requests.get(f"{TV_BASE}/account/list", headers=h, timeout=10).json()
    if accs:
        _tv_account_id = accs[0]["id"]
        _tv_username   = accs[0].get("name", TV_USER)
    log.info("✅  Tradovate connected  account_id=%s", _tv_account_id)

def _tv_headers():
    global _tv_token, _tv_token_time
    with _tv_lock:
        # Re-auth every 55 minutes
        if _tv_token is None or (time.time() - _tv_token_time) > 3300:
            _tv_authenticate()
        return {"Authorization": f"Bearer {_tv_token}"}

def _tv_find_contract(root: str) -> tuple[str, int] | tuple[None, None]:
    """Return (contractName, contractId) for the front-month contract of root symbol."""
    h = _tv_headers()
    # Step 1: find the product to get its ID
    r = _requests.get(f"{TV_BASE}/product/find", params={"name": root}, headers=h, timeout=10)
    if r.status_code == 200:
        product = r.json()
        product_id = product.get("id")
        if product_id:
            # Step 2: get active contract maturities for this product
            r2 = _requests.get(f"{TV_BASE}/contractMaturity/deps",
                               params={"masterid": product_id}, headers=h, timeout=10)
            if r2.status_code == 200 and r2.json():
                maturities = r2.json()
                # Front month = first non-expired maturity sorted by expiry date
                maturities.sort(key=lambda m: m.get("expirationDate", ""))
                for m in maturities:
                    if not m.get("isFront") is False:
                        contract_id = m.get("id")
                        # Get the actual contract name
                        r3 = _requests.get(f"{TV_BASE}/contract/item",
                                           params={"id": contract_id}, headers=h, timeout=10)
                        if r3.status_code == 200:
                            c = r3.json()
                            return c.get("name"), c.get("id")
    # Fallback: direct find (works if user passes full name like "M6EU6")
    r4 = _requests.get(f"{TV_BASE}/contract/find", params={"name": root}, headers=h, timeout=10)
    if r4.status_code == 200:
        d = r4.json()
        return d.get("name"), d.get("id")
    log.error("Could not find Tradovate contract for symbol '%s'", root)
    return None, None

def _tv_get_balance() -> float:
    h = _tv_headers()
    r = _requests.get(f"{TV_BASE}/cashBalance/getcashbalancesnapshot",
                      params={"accountId": _tv_account_id}, headers=h, timeout=10)
    if r.status_code == 200:
        d = r.json()
        return float(d.get("totalCashValue", d.get("cashBalance", 0)))
    # Fallback
    r2 = _requests.get(f"{TV_BASE}/account/item", params={"id": _tv_account_id}, headers=h, timeout=10)
    if r2.status_code == 200:
        return float(r2.json().get("cashBalance", 0))
    return 0.0

def _tv_place_order(contract_name: str, action: str, qty: int, sl: float, tp: float) -> dict:
    """Place a bracket market order on Tradovate."""
    h = _tv_headers()
    tv_action  = "Buy"  if action == "buy"  else "Sell"
    exit_action = "Sell" if action == "buy"  else "Buy"
    payload = {
        "accountSpec": _tv_username,
        "accountId":   _tv_account_id,
        "action":      tv_action,
        "symbol":      contract_name,
        "orderQty":    qty,
        "orderType":   "Market",
        "isAutomated": True,
        "bracket1": {
            "action":    exit_action,
            "orderType": "Stop",
            "stopPrice": sl,
            "qty":       qty,
        },
        "bracket2": {
            "action":    exit_action,
            "orderType": "Limit",
            "price":     tp,
            "qty":       qty,
        },
    }
    r = _requests.post(f"{TV_BASE}/order/placeorder", json=payload, headers=h, timeout=15)
    r.raise_for_status()
    return r.json()

# ── TradeLocker client ─────────────────────────────────────────────────────
_tl = None
_tl_lock = threading.Lock()

def get_tl():
    global _tl
    with _tl_lock:
        if _tl is None:
            from tradelocker import TLAPI
            log.info("Connecting to TradeLocker  env=%s  server=%s", ENVIRONMENT, TL_SERVER)
            _tl = TLAPI(
                environment=ENVIRONMENT,
                username=TL_EMAIL,
                password=TL_PASSWORD,
                server=TL_SERVER,
            )
            log.info("✅  TradeLocker connected!")
        return _tl

def get_balance(tl, account_id: int | None = None) -> tuple[float | None, float | None]:
    """Return (equity, free_margin) for an account. Uses get_account_state for live free margin."""
    try:
        # get_account_state returns live state including free margin for the currently selected account
        state = tl.get_account_state()
        log.info("Account state keys: %s", list(state.keys()) if isinstance(state, dict) else state)
        equity = None
        free_m = None
        if isinstance(state, dict):
            for k in ["accountBalance", "balance", "equity", "Equity", "Balance"]:
                if k in state:
                    equity = float(state[k])
                    break
            for k in ["freemargin", "freeMargin", "free_margin", "availableMargin",
                       "marginAvailable", "availableFunds", "freeBalance", "availableBalance"]:
                if k in state:
                    free_m = float(state[k])
                    break
        log.info("Account %s equity=%s free_margin=%s", account_id, equity, free_m)
        return equity, free_m
    except Exception as e:
        log.warning("get_account_state failed (%s), falling back to get_all_accounts", e)

    try:
        accounts = tl.get_all_accounts()
        row = accounts[accounts["id"] == account_id] if account_id and "id" in accounts.columns else accounts
        if hasattr(row, "empty") and row.empty:
            row = accounts
        for col in ["accountBalance", "balance", "equity", "Balance", "Equity"]:
            if col in accounts.columns:
                equity = float(row[col].iloc[0])
                log.info("Account %s equity=%.2f (fallback, no free_margin)", account_id, equity)
                return equity, None
    except Exception as e2:
        log.warning("Could not fetch balance: %s", e2)
    return None, None

def calc_lot_size(balance: float, entry: float, sl: float, risk_pct: float | None = None,
                  free_margin: float | None = None, leverage: int = 100) -> float:
    """Calculate lot size based on % account risk. Uses risk_pct if provided, else config default.
    free_margin (if provided) is used for margin cap instead of total balance."""
    pct = risk_pct if risk_pct is not None else RISK_PCT
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return MIN_LOT
    # Risk is always % of free margin (available funds), not total equity
    risk_base = free_margin if free_margin and free_margin > 0 else balance
    risk_dollars = risk_base * (pct / 100.0)
    lot = risk_dollars / (sl_distance * POINT_VALUE)
    lot = round(lot, 2)
    lot = max(MIN_LOT, min(MAX_LOT, lot))
    # Margin cap: never use more than 25% of available free margin (or 20% of equity as fallback).
    margin_per_lot = entry / leverage
    if margin_per_lot > 0:
        cap_amount = free_margin * 0.25 if free_margin and free_margin > 0 else balance * 0.20
        max_lot_by_margin = round(cap_amount / margin_per_lot, 2)
        max_lot_by_margin = max(MIN_LOT, max_lot_by_margin)
        if lot > max_lot_by_margin:
            log.info("Margin cap: reducing lot %.2f → %.2f (free_margin=%.2f, cap=%.2f, margin/lot=%.2f)",
                     lot, max_lot_by_margin, free_margin or 0, cap_amount, margin_per_lot)
            lot = max_lot_by_margin
    log.info(
        "Risk calc: free_margin=%.2f  risk=%.2f%%=$%.2f  SL_dist=%.2f  → lot=%.2f",
        risk_base, pct, risk_dollars, sl_distance, lot,
    )
    return lot

# ── Flask app ──────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/tl/webhook", methods=["POST"])
@app.route("/nt/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    log.info("WEBHOOK ← %s", data)

    # Auth — secret in URL (?secret=...) OR in JSON body
    url_secret  = request.args.get("secret", "")
    body_secret = data.get("secret", "")
    if url_secret != WEBHOOK_SECRET and body_secret != WEBHOOK_SECRET:
        log.warning("Bad secret")
        return jsonify({"error": "unauthorized"}), 403

    # Required fields
    for field in ["action", "symbol", "entry", "sl"]:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 422

    action = data["action"].lower()
    symbol = str(data.get("symbol") or data.get("ticker", "NAS100")).upper()
    entry  = float(data["entry"])
    sl     = float(data["sl"])
    # Always use 3R take profit regardless of what TradingView sends
    sl_dist = abs(entry - sl)
    tp = round(entry + (3 * sl_dist), 2) if action == "buy" else round(entry - (3 * sl_dist), 2)

    if action not in ("buy", "sell"):
        return jsonify({"error": f"Unknown action: {action}"}), 422

    # ── Respond to TradingView immediately (avoids 3s timeout) ───────────────
    def process_trade():
        try:
            tl = get_tl()
            risk_pct_override = float(data["risk_pct"]) if "risk_pct" in data else None

            # ── Instrument lookup (same for all accounts) ──────────────────
            aliases = {
                "US30": "DJ30",  "DJ30":  "US30",
                "XAUUSD": "GOLD","GOLD":  "XAUUSD",
                "NAS100": "USTEC","USTEC": "NAS100",
                "SPX500": "US500","US500": "SPX500",
            }
            instrument_id = tl.get_instrument_id_from_symbol_name(symbol)
            if not instrument_id:
                alt = aliases.get(symbol)
                if alt:
                    instrument_id = tl.get_instrument_id_from_symbol_name(alt)
                    if instrument_id:
                        log.info("Symbol alias: %s → %s", symbol, alt)
            if not instrument_id:
                log.error("Symbol '%s' not found", symbol)
                return

            # ── Build account map: {account_id: acc_num} ──────────────────
            all_accounts = tl.get_all_accounts()
            acct_map = {}
            if "id" in all_accounts.columns and "accNum" in all_accounts.columns:
                for _, row in all_accounts.iterrows():
                    acct_map[int(row["id"])] = int(row["accNum"])
            log.info("Account map: %s", acct_map)

            # ── Place order on every configured account ────────────────────
            account_ids = TL_ACCOUNT_IDS if TL_ACCOUNT_IDS else [None]
            for acct_id in account_ids:
                try:
                    if acct_id and acct_id in acct_map:
                        acc_num = acct_map[acct_id]
                        tl._set_account_id_and_acc_num(account_id=acct_id, acc_num=acc_num)
                        log.info("Switching to account %s (acc_num=%s)", acct_id, acc_num)
                    elif acct_id:
                        log.error("❌  Account %s not found in TradeLocker — skipping", acct_id)
                        continue

                    balance, free_margin = get_balance(tl, acct_id)
                    if not balance or balance <= 0:
                        log.error("❌  Balance fetch failed for account %s — skipping", acct_id)
                        continue
                    leverage = TL_LEVERAGE_MAP.get(acct_id, 100) if acct_id else 100
                    qty = calc_lot_size(balance, entry, sl, risk_pct=risk_pct_override, free_margin=free_margin, leverage=leverage)

                    log.info(
                        "ORDER [acct=%s] → %s %s x%.2f  entry=%.5f  sl=%.5f  tp=%.5f",
                        acct_id, action.upper(), symbol, qty, entry, sl, tp,
                    )

                    order_id = tl.create_order(
                        instrument_id,
                        quantity=qty,
                        side=action,
                        type_="market",
                        stop_loss=sl,
                        stop_loss_type="absolute",
                        take_profit=tp,
                        take_profit_type="absolute",
                    )

                    if order_id:
                        log.info("✅  [acct=%s] %s %s x%.2f  SL=%.5f  TP=%.5f  order_id=%s",
                                 acct_id, action.upper(), symbol, qty, sl, tp, order_id)
                        # Fix TP to be exactly 3R from actual fill price
                        try:
                            import time as _time
                            _time.sleep(1)  # brief wait for fill to register
                            pos_id = tl.get_position_id_from_order_id(order_id)
                            if pos_id:
                                positions = tl.get_all_positions()
                                pos_row = positions[positions["id"] == pos_id] if "id" in positions.columns else pd.DataFrame()
                                fill_col = next((c for c in ["avgPrice", "price", "openPrice", "entryPrice"] if c in positions.columns), None)
                                if not pos_row.empty and fill_col:
                                    fill_price = float(pos_row[fill_col].iloc[0])
                                    real_sl_dist = abs(fill_price - sl)
                                    real_tp = round(fill_price + (3 * real_sl_dist), 2) if action == "buy" else round(fill_price - (3 * real_sl_dist), 2)
                                    if abs(real_tp - tp) > 0.5:  # only modify if meaningfully different
                                        ok = tl.modify_position(pos_id, {"takeProfit": real_tp, "takeProfitType": "absolute"})
                                        log.info("🎯  [acct=%s] TP corrected fill=%.5f SL_dist=%.2f old_tp=%.5f → new_tp=%.5f (3R) ok=%s",
                                                 acct_id, fill_price, real_sl_dist, tp, real_tp, ok)
                                    else:
                                        log.info("✅  [acct=%s] TP already accurate (fill=%.5f, tp=%.5f)", acct_id, fill_price, tp)
                        except Exception as tp_err:
                            log.warning("⚠️  [acct=%s] TP correction failed: %s", acct_id, tp_err)
                    else:
                        log.error("❌  [acct=%s] Order returned no ID", acct_id)

                except Exception as exc:
                    log.error("❌  [acct=%s] %s", acct_id, exc)

        except Exception as exc:
            log.error("❌  %s", exc)
            global _tl
            with _tl_lock:
                _tl = None   # force re-auth on next request

    t = threading.Thread(target=process_trade, daemon=True)
    t.start()
    return jsonify({"status": "received", "action": action, "symbol": symbol}), 200


@app.route("/tradovate/webhook", methods=["POST"])
def tradovate_webhook():
    data = request.get_json(silent=True) or {}
    log.info("TRADOVATE WEBHOOK ← %s", data)

    # Auth
    url_secret  = request.args.get("secret", "")
    body_secret = data.get("secret", "")
    if url_secret != WEBHOOK_SECRET and body_secret != WEBHOOK_SECRET:
        log.warning("Bad secret on /tradovate/webhook")
        return jsonify({"error": "unauthorized"}), 403

    for field in ["action", "symbol", "sl", "tp"]:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 422

    action = data["action"].lower()
    symbol = str(data.get("symbol") or data.get("ticker", "NAS100")).upper()   # root symbol e.g. "MES"
    sl     = float(data["sl"])
    tp     = float(data["tp"])
    entry  = float(data.get("entry", 0))

    if action not in ("buy", "sell"):
        return jsonify({"error": f"Unknown action: {action}"}), 422

    if not TV_USER or not TV_PASS:
        return jsonify({"error": "Tradovate credentials not configured on server"}), 503

    def process():
        try:
            # Find front-month contract
            contract_name, _ = _tv_find_contract(symbol)
            if not contract_name:
                log.error("Tradovate: contract not found for symbol '%s'", symbol)
                return

            # Position sizing: risk RISK_PCT% of balance
            balance = _tv_get_balance()
            point_val = tv_point_value(symbol)
            sl_dist = abs((entry if entry else sl) - sl)
            if sl_dist > 0 and balance > 0 and point_val > 0:
                risk_dollars = balance * (RISK_PCT / 100.0)
                qty = max(1, round(risk_dollars / (sl_dist * point_val)))
            else:
                qty = int(data.get("qty", 1))

            log.info("Tradovate ORDER → %s %s x%d  SL=%.2f  TP=%.2f  balance=%.2f",
                     action.upper(), contract_name, qty, sl, tp, balance)

            result = _tv_place_order(contract_name, action, qty, sl, tp)
            order_id = result.get("orderId") or result.get("id") or str(result)
            log.info("✅  Tradovate %s %s x%d  order_id=%s", action.upper(), contract_name, qty, order_id)

        except Exception as exc:
            log.error("❌  Tradovate order error: %s", exc)
            with _tv_lock:
                global _tv_token
                _tv_token = None   # force re-auth next time

    threading.Thread(target=process, daemon=True).start()
    return jsonify({"status": "received", "broker": "tradovate", "action": action, "symbol": symbol}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":        "ok",
        "service":       "tradelocker+tradovate-bot",
        "environment":   ENVIRONMENT,
        "server":        TL_SERVER,
        "risk_pct":      RISK_PCT,
        "tradovate":     "configured" if TV_USER else "not configured",
    }), 200


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("TradeLocker Bot  |  server=%s  risk=%.1f%%", TL_SERVER, RISK_PCT)
    log.info("Config: %s", CONFIG_FILE)
    log.info("=" * 60)

    if not TL_PASSWORD:
        log.error("TL_PASSWORD not set in %s", CONFIG_FILE)
    else:
        try:
            tl = get_tl()
            bal, fm = get_balance(tl)
            if bal:
                log.info("Account balance: $%.2f  free_margin: %s  →  max risk per trade: $%.2f",
                         bal, fm, bal * RISK_PCT / 100)
        except Exception as e:
            log.error("Startup error: %s", e)

    app.run(host="0.0.0.0", port=5002, debug=False)
