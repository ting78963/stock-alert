#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only Fugle daily-calendar 404 comparison. No secrets printed."""
import json, os, re, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from datetime import date

DAY="2026-10-12"
START="2026-10-02"
SYMBOLS=("2323","2324")
BASE="https://api.fugle.tw/marketdata/v1.0/stock"
def token():
    t=os.environ.get("FUGLE_API_KEY","").strip()
    if t:return t
    home=Path.home()
    names=("Fugle_live_KBar_test_ready.py","Fugle_historical_5day_volume_test_ready.py","Fugle_snapshot_strong_test_ready.py")
    roots=[home/"Desktop",home/"Downloads",home/"Documents"]
    patterns=[r'(?m)^\\s*API_KEY\\s*=\\s*["\\\']([^"\\\']{16,})["\\\']',r'(?m)^\\s*FUGLE_API_KEY\\s*=\\s*["\\\']([^"\\\']{16,})["\\\']']
    seen=set()
    for root in roots:
        if not root.exists():continue
        candidates=[]
        for name in names:
            candidates.extend(root.rglob(name))
        candidates.extend(root.rglob("Fugle*.py"))
        for path in candidates:
            if path in seen or path.resolve()==Path(__file__).resolve():continue
            seen.add(path)
            try: body=path.read_text(encoding="utf-8",errors="ignore")
            except OSError:continue
            for pattern in patterns:
                match=re.search(pattern,body)
                if match:
                    print("API key source: existing local Fugle script (value hidden)")
                    return match.group(1).strip()
    raise SystemExit("STOP: Fugle key not found in environment or existing local scripts; do not paste key into chat.")
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
