# -*- coding: utf-8 -*-
"""Central Bank of Taiwan daily interbank USD/TWD close. No live quote claims."""
from __future__ import annotations
from datetime import date
from math import isfinite
import requests
from taiex_market_history_v1 import snapshot as moving_average_snapshot

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
    client=session or requests
    response=client.get(URL,timeout=timeout)
    response.raise_for_status()
    return parse_daily(response.json())

def trend_snapshot(rows,as_of):
    data=moving_average_snapshot(rows,as_of)
    data["schema"]="usdtwd_cbc_daily_ma_v1"
    data["source"]="cbc_interbank_daily_close"
    data["quote_kind"]="official_daily_close"
    data["direction"]="TWD_depreciation" if len(rows)>=2 and data["last_close"] is not None and data["last_close"]>sorted(rows,key=lambda x:x["date"])[-2]["close"] else None
    return data
