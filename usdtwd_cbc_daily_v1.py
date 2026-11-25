# -*- coding: utf-8 -*-
"""Central Bank of Taiwan daily interbank USD/TWD close. No live quote claims."""
from __future__ import annotations
from datetime import date
from math import isfinite
from taiex_market_history_v1 import normalize_daily

URL="https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day"

def parse_daily(payload):
    """Normalize CBC records to date/close; reject unrecognized schemas."""
    if isinstance(payload,dict):
        for key in ("data","Data","DataSet","dataset","records"):
            if isinstance(payload.get(key),list):
                payload=payload[key]
                break
    if not isinstance(payload,list):
        raise ValueError("Unrecognized CBC daily data format")
    result={}
    for item in payload:
        if not isinstance(item,dict):
            raise ValueError("Unexpected CBC row")
        d=next((item[k] for k in ("日期","期間","date","Date") if k in item),None)
        v=next((item[k] for k in ("NTD/USD","NTD_USD","匯率","close") if k in item),None)
        if d is None or v is None:
            raise ValueError("CBC date/rate columns not found")
        raw=str(d).strip().replace("/","-")
        if len(raw)==8 and raw.isdigit():
            raw=f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        day=date.fromisoformat(raw[:10]).isoformat()
        rate=float(str(v).replace(",","").strip())
        if not isfinite(rate) or rate<=0:
            raise ValueError("Invalid CBC USD/TWD close")
        if day in result and result[day]!=rate:
            raise ValueError("Conflicting CBC USD/TWD close")
        result[day]=rate
    return [{"date":d,"close":result[d]} for d in sorted(result)]

def fetch_daily(session=None,timeout=15):
    if session is None:
        import requests
        session=requests
    client=session
    response=client.get(URL,timeout=timeout)
    response.raise_for_status()
    return parse_daily(response.json())

def trend_snapshot(rows,as_of):
    """Only last published CBC daily closes before report date; MA5/MA20 only."""
    report_day=date.fromisoformat(str(as_of)[:10]).isoformat()
    prior=[r for r in normalize_daily(rows) if r["date"]<report_day]
    values=[r["close"] for r in prior]
    ma5=round(sum(values[-5:])/5,4) if len(values)>=5 else None
    ma20=round(sum(values[-20:])/20,4) if len(values)>=20 else None
    def ma(n, offset=0):
        end=len(values)-offset
        return sum(values[end-n:end])/n if end>=n else None
    def slope(n):
        a,b=ma(n),ma(n,1)
        return "待確認" if a is None or b is None else "上揚" if a>b else "下彎" if a<b else "持平"
    cross="無新交叉"
    if len(values)>=21:
        gap=(ma(5)-ma(20))/ma(20)
        prior_gap=(ma(5,1)-ma(20,1))/ma(20,1)
        if prior_gap<=0<gap: cross="死亡交叉"
        elif prior_gap>=0>gap: cross="黃金交叉"
        elif 0<abs(gap)<=0.0075 and abs(gap)<abs(prior_gap):
            cross="準備黃金交叉" if gap>0 else "準備死亡交叉"
    return {
        "ma5_direction":slope(5),"ma20_direction":slope(20),"cross":cross,
        "schema":"usdtwd_cbc_daily_ma5_ma20_v1",
        "source":"cbc_interbank_daily_close",
        "quote_kind":"official_daily_close",
        "as_of":report_day,
        "last_close_date":prior[-1]["date"] if prior else None,
        "last_close":values[-1] if values else None,
        "daily_count":len(values),
        "daily_ma5":ma5,
        "daily_ma20":ma20,
        "ma5_vs_ma20":("above" if ma5>ma20 else "below" if ma5<ma20 else "equal") if ma5 is not None and ma20 is not None else None,
        "direction":("TWD_depreciation" if values[-1]>values[-2] else
                     "TWD_appreciation" if values[-1]<values[-2] else
                     "unchanged") if len(values)>=2 else None,
    }
