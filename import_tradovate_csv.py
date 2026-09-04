#!/usr/bin/env python3
"""
Import Tradovate Performance CSV into tradovate_trades.json.
Usage: python3 import_tradovate_csv.py [path/to/Performance.csv]
If no path given, looks for ~/Downloads/Performance*.csv (most recent).
Uses buyFillId+sellFillId as dedup key — safe to re-import the same CSV.
"""
import csv, json, sys, glob
from pathlib import Path
from datetime import datetime, timezone

BOT = Path.home() / "tradelocker-bot"

# Detect broker from filename — Performance (1).csv etc can come from TPT
def detect_broker(path):
    name = Path(path).name.lower()
    # TPT CSVs live in Downloads but our own Tradovate CSVs are in BOT dir
    p = Path(path).resolve()
    if str(p).startswith(str(Path.home() / "Downloads")):
        return "TakeProfitTrader", BOT / "tpt_trades.json", "tpt"
    return "Tradovate", BOT / "tradovate_trades.json", "tv"

MULT = {"MES": 5, "MNQ": 2, "M2K": 5, "MGC": 10, "M6A": 10000, "M6E": 12500,
        "ES": 50, "NQ": 20, "GC": 100, "MCL": 100}

def get_mult(sym):
    for k, v in MULT.items():
        if sym.upper().startswith(k):
            return v
    return 1

def parse_pnl(raw):
    raw = str(raw).strip()
    neg = "(" in raw
    val = raw.replace("$","").replace("(","").replace(")","").replace(",","")
    try:
        v = float(val)
        return -v if neg else v
    except:
        return 0.0

def to_iso(ts_str):
    ts_str = ts_str.strip()
    for fmt in ["%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
        try:
            dt = datetime.strptime(ts_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except:
            pass
    return ts_str

# ── Find CSV ──────────────────────────────────────────────────────────────────
if len(sys.argv) > 1:
    csv_path = Path(sys.argv[1])
else:
    candidates = glob.glob(str(Path.home() / "Downloads" / "Performance*.csv"))
    if not candidates:
        print("No Performance*.csv found in ~/Downloads")
        sys.exit(0)
    csv_path = Path(max(candidates, key=lambda p: Path(p).stat().st_mtime))

BROKER, OUT, ID_PREFIX = detect_broker(csv_path)
print(f"Importing: {csv_path}  →  broker={BROKER}")

# ── Parse CSV ─────────────────────────────────────────────────────────────────
rows = []
try:
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym    = row.get("symbol","").strip()
            if not sym:
                continue
            buy_id = row.get("buyFillId","").strip()
            sel_id = row.get("sellFillId","").strip()
            qty    = int(row.get("qty",1))
            buy_p  = float(row.get("buyPrice",0))
            sel_p  = float(row.get("sellPrice",0))
            pnl    = parse_pnl(row.get("pnl","0"))
            bought = to_iso(row.get("boughtTimestamp",""))
            sold   = to_iso(row.get("soldTimestamp",""))

            if bought <= sold:
                direction = "Long"
                open_ts, close_ts = bought, sold
                entry, exit_px = buy_p, sel_p
            else:
                direction = "Short"
                open_ts, close_ts = sold, bought
                entry, exit_px = sel_p, buy_p

            trade_id = f"{ID_PREFIX}_{min(buy_id, sel_id)}_{max(buy_id, sel_id)}"
            rows.append({
                "id":        trade_id,
                "broker":    BROKER,
                "symbol":    sym,
                "direction": direction,
                "entry":     entry,
                "exit":      exit_px,
                "size":      qty,
                "pnl":       pnl,
                "date":      open_ts,
                "exitTime":  close_ts,
                "strategy":  "Manual",
                "source":    "csv",
            })
except Exception as e:
    print(f"Error reading CSV: {e}")
    sys.exit(1)

print(f"  {len(rows)} trades in CSV  (total ${sum(r['pnl'] for r in rows):,.2f})")

# ── Merge ────────────────────────────────────────────────────────────────────
existing = json.loads(OUT.read_text()) if OUT.exists() else []
existing_ids = {t.get("id") for t in existing}
added = 0
for r in rows:
    if r["id"] not in existing_ids:
        existing.append(r)
        existing_ids.add(r["id"])
        added += 1

existing.sort(key=lambda t: t.get("date",""), reverse=True)
OUT.write_text(json.dumps(existing, indent=2))
print(f"  {added} new trades added → {len(existing)} total")
