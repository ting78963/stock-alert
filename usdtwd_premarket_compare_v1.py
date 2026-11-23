# -*- coding: utf-8 -*-
"""USD/TWD 08:55 movement versus previous comparable close. No network calls."""
from math import isfinite
from premarket_quote_policy_v1 import validate_quote

def compare_to_previous_close(live_quote, previous_close, report_at):
    """Only compare same price convention and source; never mix bank quotes and market closes."""
    checked=validate_quote("usdtwd",live_quote,report_at)
    if checked["status"]!="live":
        return {"status":checked["status"],"direction":None,"detail":checked["timestamp"]}
    if not isinstance(previous_close,dict):
        return {"status":"missing_baseline","direction":None}
    if (previous_close.get("source")!=live_quote.get("source")
            or previous_close.get("quote_kind")!=live_quote.get("quote_kind")):
        return {"status":"incomparable_baseline","direction":None}
    try:
        now=float(live_quote["value"])
        prior=float(previous_close["value"])
    except (ValueError,TypeError,KeyError):
        return {"status":"invalid_price","direction":None}
    if not all(isfinite(x) and x>0 for x in (now,prior)):
        return {"status":"invalid_price","direction":None}
    delta=now-prior
    return {
        "status":"ok",
        "direction":"TWD_depreciation" if delta>0 else "TWD_appreciation" if delta<0 else "unchanged",
        "usd_twd_change":round(delta,4),
        "usd_twd_change_percent":round(delta/prior*100,4),
        "value":now,
        "previous_close":prior,
        "timestamp":checked["timestamp"],
    }

def compare_live_to_cbc_close(live_quote, cbc_rows, report_at):
    """Indicative cross-source movement: Live-Rates now vs CBC last published close.

    This is NOT a same-source FX return. Only rows strictly before the Taiwan
    report date qualify; the chosen date and two sources remain explicit.
    """
    checked=validate_quote("usdtwd",live_quote,report_at)
    if checked["status"]!="live":
        return {"status":checked["status"],"direction":None,"detail":checked["timestamp"]}
    if live_quote.get("source")!="live_rates" or live_quote.get("quote_kind")!="market_spot":
        return {"status":"unsupported_live_source","direction":None}
    if not isinstance(cbc_rows,list):
        return {"status":"missing_baseline","direction":None}
    report_date=report_at.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Taipei")).date().isoformat()
    candidates=[]
    for row in cbc_rows:
        if not isinstance(row,dict) or not isinstance(row.get("date"),str):
            continue
        day=row["date"]
        try:
            from datetime import date
            if date.fromisoformat(day).isoformat()!=day or day>=report_date:
                continue
            value=float(row["close"])
            if isfinite(value) and value>0:
                candidates.append((day,value))
        except (ValueError,TypeError,KeyError):
            continue
    if not candidates:
        return {"status":"missing_baseline","direction":None}
    baseline_date,prior=max(candidates)
    try:
        now=float(live_quote["value"])
    except (ValueError,TypeError,KeyError):
        return {"status":"invalid_price","direction":None}
    if not isfinite(now) or now<=0:
        return {"status":"invalid_price","direction":None}
    delta=now-prior
    return {
        "status":"ok","comparison_kind":"indicative_cross_source",
        "label":"相對央行前一公布日收盤之即時變動（不同來源）",
        "direction":"TWD_depreciation" if delta>0 else "TWD_appreciation" if delta<0 else "unchanged",
        "usd_twd_change":round(delta,4),
        "usd_twd_change_percent":round(delta/prior*100,4),
        "value":now,"previous_close":prior,"previous_close_date":baseline_date,
        "live_source":"live_rates","baseline_source":"cbc_interbank_daily_close",
        "timestamp":checked["timestamp"],
    }
