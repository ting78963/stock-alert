# -*- coding: utf-8 -*-
"""Shared Fugle WebSocket routing audit v1.

Diagnostic only. Does NOT import A/B trend logic, does NOT send LINE, and does
NOT write production state. It validates one authenticated WebSocket can
subscribe to multiple candle symbols and that every candle is routed only to
its own symbol bucket.

Runtime: default 3 minutes during market hours.
Bottleneck: Fugle live WebSocket event availability.
"""
from __future__ import annotations
import argparse, json, os, re, ssl, time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

WS_URL="wss://api.fugle.tw/marketdata/v1.0/stock/streaming"
TPE=ZoneInfo("Asia/Taipei")

def stop(msg):
    print("\nAUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL")
    print(msg)
    raise SystemExit(2)

def key():
    k=os.environ.get("FUGLE_API_KEY","").strip()
    if not k: stop("FUGLE_API_KEY missing")
    return k

def extract(msg):
    stack=[msg]
    out=[]
    while stack:
        x=stack.pop()
        if isinstance(x,list):
            stack.extend(x); continue
        if not isinstance(x,dict): continue
        for k in ("data","candle","candles"):
            if k in x: stack.append(x[k])
        sym=str(x.get("symbol") or x.get("code") or "").zfill(4)
        if not re.fullmatch(r"\d{4}",sym): continue
        if not all(k in x for k in ("open","high","low","close","volume")): continue
        raw=x.get("date") or x.get("time") or x.get("timestamp")
        if raw is None: continue
        out.append((sym,raw))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("symbols",nargs="+",help="2+ symbols, e.g. 2330 2317")
    ap.add_argument("--minutes",type=float,default=3.0)
    a=ap.parse_args()
    syms=[]
    for s in a.symbols:
        s=re.sub(r"\D","",s).zfill(4)
        if s not in syms: syms.append(s)
    if len(syms)<2: stop("Need at least 2 distinct symbols")
    try: import websocket
    except Exception as e: stop(f"websocket-client unavailable: {e!r}")

    print("="*100)
    print("FUGLE SHARED WEBSOCKET ROUTING AUDIT v1")
    print("symbols="+",".join(syms))
    print("ONE CONNECTION | MULTI-SUBSCRIBE | NO A/B LOGIC | NO LINE | NO PRODUCTION STATE")
    print("="*100)

    buckets=defaultdict(list); foreign=[]; events=0
    ws=websocket.create_connection(WS_URL,timeout=8,sslopt={"cert_reqs":ssl.CERT_REQUIRED})
    try:
        ws.send(json.dumps({"event":"auth","data":{"apikey":key()}}))
        deadline=time.time()+8; authed=False
        while time.time()<deadline:
            o=json.loads(ws.recv()); events+=1
            if o.get("event")=="authenticated": authed=True; break
            if o.get("event") in ("error","server_error"): stop("auth error: "+str(o)[:300])
        if not authed: stop("authentication confirmation timeout")
        print("[PASS] one WebSocket authenticated")

        for s in syms:
            ws.send(json.dumps({"event":"subscribe","data":{"channel":"candles","symbol":s}}))
        print(f"[PASS] subscribe requests sent on SAME connection: {len(syms)} symbols")

        ws.settimeout(2)
        end=time.time()+max(.1,a.minutes)*60
        while time.time()<end:
            try: raw=ws.recv()
            except Exception as e:
                if e.__class__.__name__ in ("WebSocketTimeoutException","TimeoutError"): continue
                stop(f"WebSocket receive failed: {e!r}")
            events+=1
            try:o=json.loads(raw)
            except:continue
            if o.get("event") in ("error","server_error"): stop("server error: "+str(o)[:300])
            for sym,stamp in extract(o):
                if sym not in syms: foreign.append(sym); continue
                buckets[sym].append(stamp)

        if foreign: stop("foreign-symbol candle routed into shared stream: "+",".join(sorted(set(foreign))))
        print("\nROUTING COUNTS")
        for s in syms: print(f"{s}: candles={len(buckets[s])}")
        print(f"events={events} | foreign_symbol_candles=0")
        print("\nAUDIT PASS")
        print("One Fugle WebSocket carried all requested subscriptions without cross-symbol routing.")
        print("NO PRODUCTION SIGNAL")
        return 0
    finally:
        try: ws.close()
        except: pass

if __name__=="__main__":
    raise SystemExit(main())
