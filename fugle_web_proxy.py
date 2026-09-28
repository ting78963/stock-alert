# -*- coding: utf-8 -*-
"""Read-only Fugle market-data proxy for the static strong-stock web UI.
Keeps FUGLE_API_KEY on Render. No trading, LINE, B-state, or signal mutations.
"""
from __future__ import annotations
import os, requests
from flask import Blueprint, jsonify, request

bp=Blueprint("fugle_web_proxy",__name__,url_prefix="/public/fugle")
BASE="https://api.fugle.tw/marketdata/v1.0/stock"
EXCLUDED_INDUSTRY_CODES={"02","09","14","15","16","17","18","22","32"}
_META_CACHE={}

ALLOWED_ORIGINS={
    "https://ting78963.github.io",
    "http://localhost","http://127.0.0.1",
}

def _headers():
    key=os.environ.get("FUGLE_API_KEY","").strip()
    if not key: raise RuntimeError("FUGLE_API_KEY missing")
    return {"X-API-KEY":key,"User-Agent":"stock-alert-web-proxy/1.0"}

def _get(path,params=None):
    r=requests.get(BASE+path,params=params or {},headers=_headers(),timeout=20)
    r.raise_for_status();return r.json()

@bp.after_request
def cors(resp):
    origin=request.headers.get("Origin","")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"]=origin
        resp.headers["Vary"]="Origin"
    resp.headers["Cache-Control"]="private, max-age=5"
    return resp

def _startup_smoke_test():
    """Temporary read-only adapter verification; remove after PASS."""
    try:
        s1=_get("/snapshot/quotes/TSE",{"type":"COMMONSTOCK"})
        s2=_get("/snapshot/quotes/OTC",{"type":"COMMONSTOCK"})
        rows=(s1.get("data") or [])+(s2.get("data") or [])
        if not rows:
            raise RuntimeError("empty snapshot")
        sample=next((x for x in rows if str(x.get("symbol"))=="2330"),rows[0])
        sid=str(sample["symbol"])
        d=_get(f"/historical/candles/{sid}",{"from":"2026-09-01","to":"2026-09-28","timeframe":"D","fields":"open,high,low,close,volume","sort":"asc"})
        dr=d.get("data") or []
        if not dr:
            raise RuntimeError("empty daily")
        x=dr[-1]
        mapped={"date":str(x["date"])[:10],"open":float(x["open"]),"max":float(x["high"]),
                "min":float(x["low"]),"close":float(x["close"]),"Trading_Volume":float(x["volume"])}
        if mapped["Trading_Volume"]<=0:
            raise RuntimeError("bad daily volume")
        print(f"[FUGLE WEB SMOKE PASS] snapshot_rows={len(rows)} sample={sid} daily_rows={len(dr)} fields={sorted(mapped)}",flush=True)
    except Exception as e:
        print(f"[FUGLE WEB SMOKE FAIL] {type(e).__name__}: {e}",flush=True)

_startup_smoke_test()

@bp.get("/snapshot")
def snapshot():
    out=[];dates=set()
    for market in ("TSE","OTC"):
        d=_get(f"/snapshot/quotes/{market}",{"type":"COMMONSTOCK"})
        ds=str(d.get("date") or "")[:10]
        if ds:dates.add(ds)
        for r in d.get("data") or []:
            try:
                out.append({
                    "stock_id":str(r["symbol"]),"stock_name":str(r.get("name") or r["symbol"]),
                    "change_rate":float(r.get("changePercent") or 0),
                    "total_amount":float(r.get("tradeValue") or 0),
                    "total_volume":float(r.get("tradeVolume") or 0),
                    "close":float(r.get("closePrice") or 0),"date":ds,"market":market,
                })
            except Exception:continue
    if len(dates)!=1:return jsonify(ok=False,error="snapshot_date_mismatch",dates=sorted(dates)),502
    return jsonify(ok=True,date=next(iter(dates)),data=out)

@bp.get("/ticker/<symbol>")
def ticker(symbol):
    sid=str(symbol).zfill(4)
    d=_get(f"/intraday/ticker/{sid}")
    if str(d.get("symbol") or "")!=sid:return jsonify(ok=False,error="identity_mismatch"),502
    return jsonify(ok=True,data=d)

@bp.get("/daily/<symbol>")
def daily(symbol):
    sid=str(symbol).zfill(4)
    params={"from":request.args.get("from",""),"to":request.args.get("to",""),
            "timeframe":"D","fields":"open,high,low,close,volume","sort":"asc"}
    d=_get(f"/historical/candles/{sid}",params)
    if str(d.get("symbol") or "")!=sid:return jsonify(ok=False,error="identity_mismatch"),502
    rows=[]
    for r in d.get("data") or []:
        try:
            rows.append({"date":str(r["date"])[:10],"open":float(r["open"]),"max":float(r["high"]),
                         "min":float(r["low"]),"close":float(r["close"]),
                         "Trading_Volume":float(r["volume"])})
        except Exception:continue
    return jsonify(ok=True,symbol=sid,data=rows)

@bp.get("/intraday/<symbol>")
def intraday(symbol):
    sid=str(symbol).zfill(4)
    d=_get(f"/intraday/candles/{sid}",{"timeframe":"1"})
    rows=[]
    for r in d.get("data") or []:
        try:
            rows.append({"date":r.get("date") or r.get("time"),"open":r["open"],"high":r["high"],
                         "low":r["low"],"close":r["close"],"volume":r["volume"]})
        except Exception:continue
    return jsonify(ok=True,symbol=sid,data=rows)
