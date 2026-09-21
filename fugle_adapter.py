from __future__ import annotations
import json,os,urllib.parse,urllib.request,urllib.error
import pandas as pd
BASE="https://api.fugle.tw/marketdata/v1.0/stock"; TIMEOUT=20

class DataError(RuntimeError):pass

def api_key():
    k=os.environ.get("FUGLE_API_KEY","").strip()
    if not k:raise DataError("FUGLE_API_KEY missing")
    return k

def _get(url,key):
    req=urllib.request.Request(url,headers={"X-API-KEY":key,"Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=TIMEOUT) as r:return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:raise DataError(f"Fugle HTTP {e.code}: "+e.read().decode(errors="replace")[:300])

def _canonical_minutes(o,symbol,date,volume_scale=1.0):
    if str(o.get("symbol"))!=str(symbol) or str(o.get("timeframe"))!="1" or not o.get("data"):
        raise DataError("Fugle identity/coverage failed")
    out=[]; seen=set()
    for b in o["data"]:
        dt=pd.to_datetime(b["date"]); ds=dt.strftime("%Y-%m-%d"); ts=dt.strftime("%H:%M:%S")
        if ds!=date:
            continue
        if ts in seen:raise DataError("duplicate minute")
        seen.add(ts); z={x:b.get(x) for x in ("open","high","low","close","volume")}
        if any(v is None for v in z.values()):raise DataError("missing OHLCV")
        z["volume"]=float(z["volume"])*volume_scale
        out.append({"date":date,"stock_id":str(symbol).zfill(4),"minute":ts,**z})
    if not out:raise DataError(f"Fugle coverage failed for {symbol} {date}")
    return out

def intraday_1m(symbol,date,key=None):
    """Current trading-day 1m candles. Fugle intraday volume is in lots."""
    key=key or api_key()
    q=urllib.parse.urlencode({"timeframe":"1","sort":"asc"})
    o=_get(f"{BASE}/intraday/candles/{symbol}?{q}",key)
    response_date=str(o.get("date",""))[:10]
    if response_date!=date:raise DataError(f"Fugle intraday date mismatch: expected {date}, got {response_date}")
    # Canonical engine volume unit is shares.
    return _canonical_minutes(o,symbol,date,volume_scale=1000.0)

def historical_1m(symbol,date,key=None):
    """Historical 1m candles. Fugle historical minute volume is already shares."""
    key=key or api_key()
    q=urllib.parse.urlencode({"timeframe":"1","fields":"open,high,low,close,volume","sort":"asc"})
    o=_get(f"{BASE}/historical/candles/{symbol}?{q}",key)
    return _canonical_minutes(o,symbol,date,volume_scale=1.0)

def previous_context(symbol,date,key=None):
    """Previous complete trading-day close/volume, normalized to canonical shares."""
    key=key or api_key(); d=pd.Timestamp(date); start=(d-pd.Timedelta(days=14)).strftime("%Y-%m-%d")
    q=urllib.parse.urlencode({"timeframe":"D","from":start,"to":date,"fields":"open,high,low,close,volume","sort":"asc"})
    o=_get(f"{BASE}/historical/candles/{symbol}?{q}",key)
    if str(o.get("symbol"))!=str(symbol):raise DataError("Fugle prior-context identity failed")
    prior=[]
    for b in o.get("data",[]):
        ds=pd.to_datetime(b["date"]).strftime("%Y-%m-%d")
        if ds<date:prior.append((ds,b))
    if not prior:raise DataError("No prior trading day")
    p,b=max(prior,key=lambda x:x[0])
    pc=float(b["close"])
    # Fugle historical daily volume is lots while historical minute volume is
    # shares. Normalize daily volume to shares before AttackVR division.
    pv=float(b["volume"])*1000.0
    if pc<=0 or pv<=0:raise DataError("Invalid prior context")
    return p,pc,pv
