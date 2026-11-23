# -*- coding: utf-8 -*-
"""08:55 quote freshness gate. Pure validation; no API, no LINE delivery."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TPE=ZoneInfo("Asia/Taipei")
LIVE_KEYS=frozenset(("tx","usdtwd"))
CLOSE_KEYS=frozenset(("taiex","sox"))

def validate_quote(key, quote, report_at, max_age_seconds=180):
    """Fail closed on unknown/missing/stale timestamps; preserve source timestamps."""
    if key not in LIVE_KEYS | CLOSE_KEYS:
        raise ValueError("Unknown market indicator")
    if not isinstance(report_at, datetime) or report_at.tzinfo is None:
        raise ValueError("report_at must be timezone-aware")
    if not isinstance(quote, dict) or quote.get("value") is None:
        return {"value":None,"timestamp":"資料待取得","status":"missing"}
    raw=quote.get("quoted_at")
    try:
        ts=datetime.fromisoformat(raw.replace("Z","+00:00")) if isinstance(raw,str) else raw
        if not isinstance(ts,datetime) or ts.tzinfo is None:
            raise ValueError("missing timezone")
    except (ValueError,TypeError,AttributeError):
        return {"value":None,"timestamp":"報價時間不明","status":"invalid_time"}
    seconds=(report_at.astimezone(timezone.utc)-ts.astimezone(timezone.utc)).total_seconds()
    if seconds < -30:
        return {"value":None,"timestamp":"報價時間異常","status":"future"}
    if key in LIVE_KEYS and seconds > max_age_seconds:
        return {"value":None,"timestamp":f"報價逾時（{ts.astimezone(TPE):%H:%M:%S}）","status":"stale"}
    result={k:v for k,v in quote.items() if k in ("value","change")}
    result["timestamp"]=ts.astimezone(TPE).strftime("%Y-%m-%d %H:%M:%S")
    result["status"]="live" if key in LIVE_KEYS else "close"
    return result
