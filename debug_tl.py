#!/usr/bin/env python3
"""Debug: print raw API responses to find where trade data lives."""
import json, time, requests
from tradelocker import TLAPI

EMAIL    = "dayrelfit24@gmail.com"
PASSWORD = "Dydd11012015##"
SERVER   = "HEROFX"
BASE     = "https://live.tradelocker.com/backend-api"

tl = TLAPI(environment="https://live.tradelocker.com", username=EMAIL, password=PASSWORD, server=SERVER)
acc_df  = tl.get_all_accounts()
acc_id  = str(acc_df["id"].iloc[0])
acc_num = str(acc_df["accNum"].iloc[0])
token   = tl._access_token
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "accNum": acc_num}

print(f"acc_id={acc_id}  acc_num={acc_num}\n")

endpoints = [
    f"{BASE}/trade/accounts/{acc_id}/ordersHistory",
    f"{BASE}/trade/accounts/{acc_id}/orders",
    f"{BASE}/trade/accounts/{acc_id}/executions",
    f"{BASE}/trade/accounts/{acc_id}/positions",
    f"{BASE}/trade/accounts/{acc_id}/positions?state=closed",
]

for url in endpoints:
    time.sleep(1)  # avoid rate limit
    r = requests.get(url, headers=h, timeout=15)
    short = url.split(acc_id)[-1]
    raw = r.text[:600]
    print(f"── {short} [{r.status_code}] ──")
    print(raw)
    print()
