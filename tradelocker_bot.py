#!/usr/bin/env python3
"""
TradeLocker Webhook Bot

Port    : 5002
Endpoint: POST /tl/webhook?secret=<WEBHOOK_SECRET>  (also /nt/webhook)
Health  : GET  /health
"""

import os, logging, threading
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
RISK_PCT        = float(cfg.get("RISK_PCT", "1.5"))     # % of balance to risk
POINT_VALUE     = float(cfg.get("POINT_VALUE", "1.0"))  # USD per point per 1 lot
MIN_LOT         = float(cfg.get("MIN_LOT",  "0.01"))
MAX_LOT         = float(cfg.get("MAX_LOT",  "50.0"))
WEBHOOK_SECRET  = cfg.get("WEBHOOK_SECRET", os.getenv("WEBHOOK_SECRET", "tradelocker_dayrel_2026"))

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

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

def get_balance(tl) -> float | None:
    """Try to get account balance from TLAPI."""
    try:
        accounts = tl.get_all_accounts()
        log.info("Accounts columns: %s", list(accounts.columns))
        # Try common column names
        for col in ["accountBalance", "balance", "equity", "Balance", "Equity"]:
            if col in accounts.columns:
                val = float(accounts[col].iloc[0])
                log.info("Account balance (%s): %.2f", col, val)
                return val
        log.warning("Balance column not found. Available: %s", list(accounts.columns))
    except Exception as e:
        log.warning("Could not fetch balance: %s", e)
    return None

def calc_lot_size(balance: float, entry: float, sl: float, risk_pct: float | None = None) -> float:
    """Calculate lot size based on % account risk. Uses risk_pct if provided, else config default."""
    pct = risk_pct if risk_pct is not None else RISK_PCT
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return MIN_LOT
    risk_dollars = balance * (pct / 100.0)
    lot = risk_dollars / (sl_distance * POINT_VALUE)
    lot = round(lot, 2)
    lot = max(MIN_LOT, min(MAX_LOT, lot))
    log.info(
        "Risk calc: balance=%.2f  risk=%.2f%%=%.2f  SL_dist=%.5f  point_val=%.2f  → lot=%.2f",
        balance, pct, risk_dollars, sl_distance, POINT_VALUE, lot,
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
    for field in ["action", "symbol", "entry", "sl", "tp"]:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 422

    action = data["action"].lower()
    symbol = str(data["symbol"]).upper()
    entry  = float(data["entry"])
    sl     = float(data["sl"])
    tp     = float(data["tp"])

    if action not in ("buy", "sell"):
        return jsonify({"error": f"Unknown action: {action}"}), 422

    try:
        tl = get_tl()

        # ── Position size: risk % from alert payload or config default ──
        risk_pct_override = float(data["risk_pct"]) if "risk_pct" in data else None
        balance = get_balance(tl)
        if balance and balance > 0:
            qty = calc_lot_size(balance, entry, sl, risk_pct=risk_pct_override)
        else:
            qty = float(data.get("qty", 0.1))
            log.warning("Could not get balance — using fallback qty=%.2f", qty)

        # ── Instrument lookup ──────────────────────────────────────────
        instrument_id = tl.get_instrument_id_from_symbol_name(symbol)
        if not instrument_id:
            aliases = {
                "US30": "DJ30",  "DJ30":  "US30",
                "XAUUSD": "GOLD","GOLD":  "XAUUSD",
                "NAS100": "USTEC","USTEC": "NAS100",
                "SPX500": "US500","US500": "SPX500",
            }
            alt = aliases.get(symbol)
            if alt:
                instrument_id = tl.get_instrument_id_from_symbol_name(alt)
                if instrument_id:
                    log.info("Symbol alias: %s → %s", symbol, alt)
        if not instrument_id:
            return jsonify({"error": f"Symbol '{symbol}' not found"}), 422

        log.info(
            "ORDER → %s %s x%.2f  entry=%.5f  sl=%.5f  tp=%.5f",
            action.upper(), symbol, qty, entry, sl, tp,
        )

        # ── Place market order with SL & TP ───────────────────────────
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
            log.info("✅  %s %s x%.2f  SL=%.5f  TP=%.5f  order_id=%s",
                     action.upper(), symbol, qty, sl, tp, order_id)
            return jsonify({
                "status":   "ok",
                "order_id": str(order_id),
                "qty":      qty,
                "sl":       sl,
                "tp":       tp,
            }), 200
        else:
            log.error("Order returned no ID")
            return jsonify({"error": "Order failed — no order_id returned"}), 500

    except Exception as exc:
        log.error("❌  %s", exc)
        global _tl
        with _tl_lock:
            _tl = None   # force re-auth on next request
        return jsonify({"error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":      "ok",
        "service":     "tradelocker-bot",
        "environment": ENVIRONMENT,
        "server":      TL_SERVER,
        "risk_pct":    RISK_PCT,
        "point_value": POINT_VALUE,
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
            bal = get_balance(tl)
            if bal:
                log.info("Account balance: $%.2f  →  max risk per trade: $%.2f",
                         bal, bal * RISK_PCT / 100)
        except Exception as e:
            log.error("Startup error: %s", e)

    app.run(host="0.0.0.0", port=5002, debug=False)
