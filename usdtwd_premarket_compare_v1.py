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
