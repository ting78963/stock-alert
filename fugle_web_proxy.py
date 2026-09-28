# -*- coding: utf-8 -*-
"""Read-only Fugle market-data proxy for the static strong-stock web UI.
Keeps FUGLE_API_KEY on Render. No trading, LINE, B-state, or signal mutations.
"""
from __future__ import annotations
import os, requests
from datetime import datetime, timedelta
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
    from_s=str(request.args.get("from","")).strip()[:10]
    to_s=str(request.args.get("to","")).strip()[:10]
    try:
        start=datetime.strptime(from_s,"%Y-%m-%d").date()
        end=datetime.strptime(to_s,"%Y-%m-%d").date()
    except ValueError:
        return jsonify(ok=False,error="invalid_date"),400
    if start>end:
        return jsonify(ok=False,error="invalid_date_range"),400

    # Fugle historical candles requires every from~to request to be < 1 year.
    # Split long website lookbacks into conservative 330-day chunks, then
    # dedupe/merge back into the exact legacy daily shape expected by the UI.
    by_date={}
    cur=start
    while cur<=end:
        chunk_end=min(cur+timedelta(days=329),end)
        params={"from":cur.isoformat(),"to":chunk_end.isoformat(),
                "timeframe":"D","fields":"open,high,low,close,volume","sort":"asc"}
        try:
            d=_get(f"/historical/candles/{sid}",params)
        except requests.HTTPError as e:
            # Fugle documents 404 for a valid range containing no trading data.
            if e.response is not None and e.response.status_code==404:
                cur=chunk_end+timedelta(days=1)
                continue
            raise
        if str(d.get("symbol") or "")!=sid:
            return jsonify(ok=False,error="identity_mismatch"),502
        for r in d.get("data") or []:
            try:
                ds=str(r["date"])[:10]
                by_date[ds]={"date":ds,"open":float(r["open"]),"max":float(r["high"]),
                             "min":float(r["low"]),"close":float(r["close"]),
                             "Trading_Volume":float(r["volume"])}
            except Exception:
                continue
        cur=chunk_end+timedelta(days=1)
    rows=[by_date[k] for k in sorted(by_date)]
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

@bp.get("/kbar/<symbol>")
def kbar(symbol):
    sid=str(symbol).zfill(4)
    date=str(request.args.get("date","")).strip()[:10]
    if not date:
        return jsonify(ok=False,error="date_required"),400
    params={"from":date,"to":date,"timeframe":"1","fields":"open,high,low,close,volume","sort":"asc"}
    d=_get(f"/historical/candles/{sid}",params)
    if str(d.get("symbol") or "")!=sid:return jsonify(ok=False,error="identity_mismatch"),502
    rows=[]
    for r in d.get("data") or []:
        try:
            ts=str(r.get("date") or r.get("time") or "")
            if ts[:10]!=date:continue
            rows.append({"date":ts,"stock_id":sid,"open":float(r["open"]),"max":float(r["high"]),
                         "min":float(r["low"]),"close":float(r["close"]),
                         "Trading_Volume":float(r["volume"])})
        except Exception:continue
    return jsonify(ok=True,symbol=sid,date=date,data=rows)
