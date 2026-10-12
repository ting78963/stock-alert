#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only Fugle daily-calendar 404 comparison. No secrets printed."""
import json, os, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from datetime import date

DAY="2026-10-12"
START="2026-10-02"
SYMBOLS=("2323","2324")
BASE="https://api.fugle.tw/marketdata/v1.0/stock"
def token():
    t=os.environ.get("FUGLE_API_KEY","").strip()
    if t:return t
    raise SystemExit("STOP: set FUGLE_API_KEY in this PowerShell session; do not paste key into chat.")
def probe(sid,key,variant):
    p={"timeframe":"D","from":START,"to":DAY,"fields":"open,high,low,close,volume","sort":"asc"}
    if variant=="prior_only":p["to"]="2026-10-09"
    url=f"{BASE}/historical/candles/{sid}?"+urllib.parse.urlencode(p)
    req=urllib.request.Request(url,headers={"X-API-KEY":key,"Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=12) as resp:
            code=resp.status
            obj=json.loads(resp.read(2000000))
    except urllib.error.HTTPError as e:
        print(f"{sid} {variant}: HTTP {e.code} (body redacted)")
        return e.code
    except Exception as e:
        print(f"{sid} {variant}: NETWORK ERROR {type(e).__name__}")
        return None
    rows=obj.get("data",[]) if isinstance(obj,dict) else []
    dates=sorted({str(x.get("date",""))[:10] for x in rows if isinstance(x,dict)})
    print(f"{sid} {variant}: HTTP {code}; symbol_match={str(obj.get('symbol'))==sid}; timeframe={obj.get('timeframe')}; rows={len(rows)}; dates={dates}")
    return code
def main():
    print("FUGLE DAILY CALENDAR COMPARISON | READ ONLY | NO PRODUCTION WRITE")
    key=token()
    for variant in ("original","prior_only"):
        for sid in SYMBOLS:
            probe(sid,key,variant)
    print("Do not share your API key. Paste only the four result lines.")
if __name__=="__main__":main()
