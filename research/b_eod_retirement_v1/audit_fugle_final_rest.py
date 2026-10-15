# -*- coding: utf-8 -*-
"""Read-only Fugle final-minute evidence audit. NEVER writes production state.
Uses live Fugle intraday endpoint (normally current trading day only).
Do not use a response from a different date as historical evidence.
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

def audit(symbol, day):
    today=dt.datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    print("REQUESTED_DATE",day,"TAIPEI_TODAY",today,"SYMBOL",symbol,flush=True)
    if day!=today:
        print("[STOP] Fugle intraday endpoint is not proven to serve historical dates; no request sent.")
        return 2
    key=os.environ.get("FUGLE_API_KEY","").strip()
    if not key:
        print("[STOP] FUGLE_API_KEY unavailable; no fallback secret extraction.")
        return 2
    url="https://api.fugle.tw/marketdata/v1.0/stock/intraday/candles/"+urllib.parse.quote(symbol)+"?timeframe=1&sort=asc"
    req=urllib.request.Request(url,headers={"X-API-KEY":key,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=20) as resp:
        data=json.load(resp)
    if not isinstance(data,dict) or not isinstance(data.get("data"),list):
        print("[STOP] unexpected REST response schema")
        return 2
    if data.get("symbol") and str(data["symbol"])!=symbol:
        print("[STOP] returned symbol mismatch")
        return 2
    if data.get("timeframe") and str(data["timeframe"])!="1":
        print("[STOP] timeframe mismatch")
        return 2
    rows=data["data"]
    if not rows:
        print("[STOP] empty REST rows")
        return 2
    stamps=[]
    for i,row in enumerate(rows):
        raw=row.get("date") or row.get("time") or row.get("timestamp")
        if raw is None:
            print("[STOP] missing timestamp at",i);return 2
        if isinstance(raw,(int,float)):
            t=dt.datetime.fromtimestamp(raw/(1000 if raw>1e11 else 1),dt.timezone.utc)
        else:
            t=dt.datetime.fromisoformat(str(raw).replace("Z","+00:00"))
            if t.tzinfo is None:t=t.replace(tzinfo=ZoneInfo("Asia/Taipei"))
        t=t.astimezone(ZoneInfo("Asia/Taipei"))
        if t.date().isoformat()!=day:
            print("[STOP] REST returned a different session date:",t.isoformat());return 2
        for k in ("open","high","low","close","volume"):
            if k not in row or row[k] is None:
                print("[STOP] missing OHLCV",i,k);return 2
        stamps.append(t.strftime("%H:%M:%S"))
    if stamps!=sorted(set(stamps)):
        print("[STOP] duplicate or unordered timestamps")
        return 2
    print("[PASS] REST identity/date/schema/order",flush=True)
    print("ROW_COUNT",len(rows),"FIRST_MINUTE",stamps[0],"LAST_MINUTE",stamps[-1],flush=True)
    print("LAST_5_MINUTES",stamps[-5:],flush=True)
    print("NOTE: last minute observed does not independently prove exchange finality.")
    return 0

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--symbol",required=True)
    p.add_argument("--date",required=True)
    a=p.parse_args()
    raise SystemExit(audit(a.symbol,a.date))
