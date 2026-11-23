# -*- coding: utf-8 -*-
"""Keyless Live-Rates USD/TWD snapshot. One HTTP request per invocation, no polling."""
from datetime import datetime,timezone
from math import isfinite
from urllib.request import Request,urlopen
import json

URL="https://www.live-rates.com/rates"

def parse_usdtwd(payload):
    if not isinstance(payload,list):
        raise ValueError("Live-Rates response must be a list")
    matches=[row for row in payload if isinstance(row,dict) and row.get("currency")=="USD/TWD"]
    if len(matches)!=1:
        raise ValueError("USD/TWD missing or duplicated")
    row=matches[0]
    try:
        price=float(row["rate"])
        raw=float(row["timestamp"])
        ts=datetime.fromtimestamp(raw/1000 if raw>1e11 else raw,tz=timezone.utc)
    except (ValueError,TypeError,KeyError,OverflowError,OSError) as exc:
        raise ValueError("Invalid USD/TWD price or timestamp") from exc
    if not isfinite(price) or price<=0:
        raise ValueError("Invalid USD/TWD price")
    result={"value":price,"quoted_at":ts.isoformat(),"quote_kind":"market_spot",
            "source":"live_rates"}
    for field in ("bid","ask","close"):
        try:
            value=float(row[field])
            if isfinite(value) and value>0:
                result[field]=value
        except (KeyError,ValueError,TypeError):
            pass
    return result

def fetch_once(timeout=15,opener=None):
    opener=opener or urlopen
    req=Request(URL,headers={"User-Agent":"stock-alert-usdtwd/1.0"})
    with opener(req,timeout=timeout) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:
        raise ValueError("Live-Rates response exceeds 2 MB")
    return parse_usdtwd(json.loads(raw))
