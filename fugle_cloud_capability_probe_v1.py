# -*- coding: utf-8 -*-
"""READ-ONLY Fugle cloud capability probe.
NO SIGNAL | NO LINE | NO PRODUCTION STATE WRITE
"""
from __future__ import annotations
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE="https://api.fugle.tw/marketdata/v1.0/stock"
WS="wss://api.fugle.tw/marketdata/v1.0/stock/streaming"
TPE=ZoneInfo("Asia/Taipei")
TIMEOUT=15

def key():
    k=os.environ.get("FUGLE_API_KEY","").strip()
    if not k:
        raise RuntimeError("FUGLE_API_KEY missing")
    return k

def get(path):
    req=urllib.request.Request(
        BASE+path,
        headers={"X-API-KEY":key(),"Accept":"application/json"},
    )
    try:
        with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
            return r.status,json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body=e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {body}")

def check_snapshot(market):
    status,o=get(f"/snapshot/quotes/{market}?type=COMMONSTOCK")
    if status!=200 or o.get("market")!=market or not isinstance(o.get("data"),list) or not o["data"]:
        raise RuntimeError(f"{market} snapshot identity/coverage failed")
    sample=o["data"][0]
    needed=("symbol","name","tradeVolume","tradeValue")
    miss=[x for x in needed if x not in sample]
    if miss: raise RuntimeError(f"{market} snapshot missing fields: {miss}")
    return {"date":o.get("date"),"time":o.get("time"),"rows":len(o["data"])}

def check_intraday(symbol="2330"):
    status,o=get(f"/intraday/candles/{symbol}?timeframe=1&sort=asc")
    if status!=200 or str(o.get("symbol"))!=symbol:
        raise RuntimeError("intraday identity failed")
    data=o.get("data") or []
    return {"date":o.get("date"),"rows":len(data)}

def check_historical(symbol="2330"):
    # Probe a small completed historical window; no production semantics involved.
    today=datetime.now(TPE).date()
    end=(today-timedelta(days=1)).isoformat()
    start=(today-timedelta(days=14)).isoformat()
    q=urllib.parse.urlencode({
        "timeframe":"D","from":start,"to":end,
        "fields":"open,high,low,close,volume","sort":"asc"
    })
    status,o=get(f"/historical/candles/{symbol}?{q}")
    if status!=200 or str(o.get("symbol"))!=symbol or not (o.get("data") or []):
        raise RuntimeError("historical identity/coverage failed")
    return {"rows":len(o["data"])}

def check_websocket(symbol="2330"):
    try:
        import websocket
    except Exception as e:
        raise RuntimeError(f"websocket-client unavailable: {e}")
    ws=websocket.create_connection(WS,timeout=TIMEOUT)
    try:
        ws.send(json.dumps({"event":"auth","data":{"apikey":key()}}))
        deadline=time.time()+TIMEOUT
        authenticated=False
        while time.time()<deadline:
            msg=json.loads(ws.recv())
            if msg.get("event")=="authenticated":
                authenticated=True; break
            if msg.get("event")=="error":
                raise RuntimeError("WebSocket auth rejected: "+str(msg.get("data")))
        if not authenticated: raise RuntimeError("WebSocket auth timeout")
        ws.send(json.dumps({"event":"subscribe","data":{"channel":"candles","symbol":symbol}}))
        return {"authenticated":True,"subscription_sent":"candles:2330"}
    finally:
        try: ws.close()
        except Exception: pass

def main():
    print("="*88)
    print("FUGLE CLOUD CAPABILITY PROBE v1")
    print("READ ONLY | NO SIGNAL | NO LINE | NO PRODUCTION STATE WRITE")
    print("="*88)
    checks=[
        ("snapshot_TSE",lambda:check_snapshot("TSE")),
        ("snapshot_OTC",lambda:check_snapshot("OTC")),
        ("intraday_1m",check_intraday),
        ("historical_daily",check_historical),
        ("websocket_auth",check_websocket),
    ]
    failed=[]
    for name,fn in checks:
        try:
            result=fn()
            print(f"PASS | {name} | {json.dumps(result,ensure_ascii=False)}")
        except Exception as e:
            failed.append(name)
            print(f"FAIL | {name} | {type(e).__name__}: {e}")
    if failed:
        print("AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL")
        print("FAILED:",",".join(failed))
        return 2
    print("PASS | Fugle capabilities required by A/B are available")
    print("NO SIGNAL | NO LINE")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
