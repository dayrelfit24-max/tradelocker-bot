#!/usr/bin/env python3
"""Debug: identify contracts and show fills with correct names."""
import json, requests
from pathlib import Path

config_path = Path.home() / "tradelocker-bot" / "config.env"
config = {}
for line in config_path.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        config[k.strip()] = v.strip()

BASE = "https://live.tradovateapi.com/v1"
r = requests.post(f"{BASE}/auth/accesstokenrequest", json={
    "name": config["TV_USERNAME"], "password": config["TV_PASSWORD"],
    "appId": "Sample App", "appVersion": "1.0",
    "cid": int(config["TV_CID"]), "sec": config["TV_SECRET"],
    "deviceId": "journal-debug"
}, timeout=15)
token = r.json().get("accessToken")
print(f"Auth: {'OK' if token else 'FAILED - ' + str(r.json())}")
if not token: exit(1)

h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Get fills
fills = requests.get(f"{BASE}/fill/list", headers=h, timeout=15).json()
print(f"\n{len(fills)} fills total")

# Look up each unique contractId individually
contract_ids = list({f.get("contractId") for f in fills})
print(f"\n=== CONTRACT LOOKUP ({len(contract_ids)} unique contracts) ===")
contract_map = {}
for cid in contract_ids:
    try:
        resp = requests.get(f"{BASE}/contract/item", params={"id": cid}, headers=h, timeout=10)
        data = resp.json()
        name = data.get("name", "UNKNOWN")
        contract_map[cid] = name
        print(f"  {cid} → {name}  (full: {data})")
    except Exception as e:
        contract_map[cid] = str(cid)
        print(f"  {cid} → lookup failed: {e}")

print(f"\n=== FILLS WITH CONTRACT NAMES ===")
for f in sorted(fills, key=lambda x: x.get("timestamp","")):
    cid   = f.get("contractId")
    name  = contract_map.get(cid, str(cid))
    side  = f.get("action")
    price = f.get("price")
    qty   = f.get("qty")
    ts    = f.get("timestamp","")[:10]
    active = f.get("active")
    paired = f.get("finallyPaired")
    print(f"  {ts}  {name:10s}  {side:4s}  price={price}  qty={qty}  active={active}  paired={paired}")
