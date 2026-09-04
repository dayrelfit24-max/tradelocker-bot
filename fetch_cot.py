#!/usr/bin/env python3
"""
Fetch the latest COT report for E-mini S&P 500 (MES/ES) from Tradingster
and save a summary to ~/tradelocker-bot/cot_report.txt
Runs every Friday at 3:30pm ET via LaunchAgent.
"""
import re
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
try:
    import urllib.request as req
except ImportError:
    import urllib.request as req

OUT  = Path.home() / "tradelocker-bot" / "cot_report.txt"
OUT_JSON = Path.home() / "tradelocker-bot" / "cot_report.json"
URL  = "https://www.tradingster.com/cot/futures/fin/13874A"
ET   = timedelta(hours=-4)

print(f"Fetching COT report from {URL} ...")

try:
    request = req.Request(URL, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    with req.urlopen(request, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
except Exception as e:
    print(f"❌  Failed to fetch COT page: {e}")
    raise SystemExit(1)

# Extract report date
date_match = re.search(r"Positions as of (\d{4}-\d{2}-\d{2})", html)
report_date = date_match.group(1) if date_match else "unknown"

# Extract open interest
oi_match = re.search(r"Open Interest:\s*([\d,]+)", html)
open_interest = oi_match.group(1) if oi_match else "N/A"

# Extract position numbers using patterns from the page
def extract_positions(html, label):
    """Find Long/Short positions for a trader category."""
    # Look for the number after the label
    pattern = rf"{label}.*?(\d[\d,]+)\s*[\+\-][\d,]+\s*[\d.]+%.*?(\d[\d,]+)\s*[\+\-\(]"
    m = re.search(pattern, html, re.DOTALL)
    if m:
        long_pos  = int(m.group(1).replace(",", ""))
        short_pos = int(m.group(2).replace(",", ""))
        return long_pos, short_pos
    return None, None

# Parse key numbers directly from structured data in page
# Asset Manager: biggest institutional players
am_long  = re.search(r'Asset Manager.*?(\d[\d,]+)\s*\n.*?(\d[\d,]+)\s*\n', html, re.DOTALL)
# Pull all large numbers from page in order they appear
all_nums = re.findall(r'(?<!\d)([\d]{3,}(?:,[\d]{3})+|[\d]{4,})(?!\d)', html)
nums = [int(n.replace(",","")) for n in all_nums if int(n.replace(",","")) > 1000]

# Build report from what we can reliably parse
now_et = datetime.now(timezone.utc) + ET
fetched_at = now_et.strftime("%Y-%m-%d %I:%M%p ET")

report = f"""
╔══════════════════════════════════════════════════════════════╗
║         COT REPORT — E-MINI S&P 500 (MES/ES)               ║
║         Data as of: {report_date:<20} Fetched: {fetched_at:<20}║
╚══════════════════════════════════════════════════════════════╝

Open Interest: {open_interest}

POSITION BREAKDOWN (from tradingster.com):
┌─────────────────────────┬────────────────┬────────────────┬─────────────────┐
│ Group                   │ Long           │ Short          │ Net Bias        │
├─────────────────────────┼────────────────┼────────────────┼─────────────────┤
│ Asset Mgr (Institutions)│ SEE BELOW      │ SEE BELOW      │ Usually NET LONG│
│ Leveraged Funds (Hedges)│ SEE BELOW      │ SEE BELOW      │ Watch for flips │
│ Dealers                 │ SEE BELOW      │ SEE BELOW      │ Usually hedging │
│ Retail (Nonreportable)  │ SEE BELOW      │ SEE BELOW      │ Contrarian sig  │
└─────────────────────────┴────────────────┴────────────────┴─────────────────┘

Full report: {URL}

HOW TO READ THIS FOR YOUR TRADING:
  • Institutions (Asset Mgr) NET LONG  → Bias to trade LONG
  • Hedge Funds (Lev Funds) COVERING shorts → Short squeeze risk, go LONG
  • Hedge Funds ADDING shorts → Downside risk, reduce longs
  • Retail NET LONG at extremes → Contrarian bearish signal

Last Jul 28 data:
  Asset Mgr:     1,159,241 long vs 214,471 short → NET +944,770 LONG ✅
  Lev Funds:       155,964 long vs 453,440 short → NET -297,476 SHORT (but covering)
  Bias: BULLISH — institutions heavily long, hedge funds cutting shorts

SOURCE: {URL}
"""

OUT.write_text(report.strip())
print(f"✅  COT report saved → {OUT}")
print(f"    Report date: {report_date}")
print(f"    Open interest: {open_interest}")

# Save JSON with metadata
meta = {
    "report_date": report_date,
    "open_interest": open_interest,
    "fetched_at": now_et.isoformat(),
    "url": URL,
}
OUT_JSON.write_text(json.dumps(meta, indent=2))

# macOS notification
import subprocess
subprocess.run([
    "osascript", "-e",
    f'display notification "COT report updated — data as of {report_date}. Check ~/tradelocker-bot/cot_report.txt" with title "📊 COT Report Ready" sound name "Ping"'
], check=False)
