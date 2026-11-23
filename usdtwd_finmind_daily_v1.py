# -*- coding: utf-8 -*-
"""Normalize FinMind TaiwanExchangeRate daily bank quotes; never label as live."""
from datetime import date
from math import isfinite

def normalize_daily_bank_quotes(rows, as_of):
    today=date.fromisoformat(str(as_of)[:10]).isoformat()
    result={}
    for item in rows:
        if not isinstance(item,dict):
            continue
        day=str(item.get("date",""))[:10]
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        if day>=today:
            continue  # Avoid unfinished/current-day rows.
        field="spot_sell" if item.get("spot_sell") not in (None,"") else "cash_sell"
        try:
            price=float(item[field])
        except (ValueError,TypeError,KeyError):
            continue
        if not isfinite(price) or price<=0:
            continue
        if day in result and result[day]["value"]!=price:
            raise ValueError("Conflicting FX values for one date")
        result[day]={"date":day,"value":price,"source":"finmind_TaiwanExchangeRate",
                     "quote_kind":"bank_"+field,"is_live":False}
    return [result[d] for d in sorted(result)]

def previous_daily_change(rows,as_of):
    data=normalize_daily_bank_quotes(rows,as_of)
    if len(data)<2:
        return {"status":"insufficient_daily_history","is_live":False}
    current,previous=data[-1],data[-2]
    if current["quote_kind"]!=previous["quote_kind"]:
        return {"status":"incomparable_bank_quote_types","is_live":False}
    delta=current["value"]-previous["value"]
    return {"status":"ok","is_live":False,"date":current["date"],
            "quote_kind":current["quote_kind"],"value":current["value"],
            "previous_date":previous["date"],"previous_value":previous["value"],
            "direction":"TWD_depreciation" if delta>0 else "TWD_appreciation" if delta<0 else "unchanged"}
