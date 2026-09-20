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

def historical_1m(symbol,date,key=None):
    key=key or api_key(); q=urllib.parse.urlencode({"timeframe":"1","from":date,"to":date,"fields":"open,high,low,close,volume,average","sort":"asc"})
    o=_get(f"{BASE}/historical/candles/{symbol}?{q}",key)
    if str(o.get("symbol"))!=str(symbol) or str(o.get("timeframe"))!="1" or not o.get("data"):raise DataError("Fugle identity/coverage failed")
    out=[]; seen=set()
    for b in o["data"]:
        dt=pd.to_datetime(b["date"]); ds=dt.strftime("%Y-%m-%d"); ts=dt.strftime("%H:%M:%S")
        if ds!=date or ts in seen:raise DataError("date leakage or duplicate minute")
        seen.add(ts); z={x:b.get(x) for x in ("open","high","low","close","volume")}
        if any(v is None for v in z.values()):raise DataError("missing OHLCV")
        out.append({"date":date,"stock_id":str(symbol).zfill(4),"minute":ts,**z})
    return out

def previous_context(symbol,date,key=None):
    key=key or api_key(); d=pd.Timestamp(date); start=(d-pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    q=urllib.parse.urlencode({"timeframe":"D","from":start,"to":date,"fields":"open,high,low,close,volume","sort":"asc"})
    o=_get(f"{BASE}/historical/candles/{symbol}?{q}",key)
    dates=[pd.to_datetime(b["date"]).strftime("%Y-%m-%d") for b in o.get("data",[]) if pd.to_datetime(b["date"]).strftime("%Y-%m-%d")<date]
    if not dates:raise DataError("No prior trading day")
    p=max(dates); rows=historical_1m(symbol,p,key)
    df=pd.DataFrame(rows).sort_values("minute",kind="stable")
    pc=float(pd.to_numeric(df["close"]).iloc[-1]); pv=float(pd.to_numeric(df["volume"]).clip(lower=0).sum())
    if pc<=0 or pv<=0:raise DataError("Invalid prior context")
    return p,pc,pv
