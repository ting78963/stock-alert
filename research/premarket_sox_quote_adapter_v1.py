"""Convert validated Yahoo daily SOX bars to the original brief quote contract."""
from datetime import datetime, time
from zoneinfo import ZoneInfo
from math import isfinite
from research.premarket_sox_yahoo_chart_v1 import fetch_sox_chart

def fetch_sox_quote(report_at, fetcher=fetch_sox_chart):
    try:
        row = fetcher()
        if not row.get("available") or row.get("source") != "yahoo_chart_sox":
            return None
        us = ZoneInfo("America/New_York")
        day = datetime.fromisoformat(row["close_date"]).date()
        stamp = datetime.combine(day, time(16), us)
        age = (report_at - stamp).total_seconds()
        close, prev = float(row["close"]), float(row["previous_close"])
        if not all(isfinite(x) and x > 0 for x in (close, prev)) or not 0 <= age <= 4*86400:
            return None
        return {"value": f"{close:,.2f}", "previous_close": f"{prev:,.2f}", "change": f"{close-prev:+,.2f} ({(close/prev-1)*100:+.2f}%)", "quoted_at": stamp.isoformat(), "source": "yahoo_chart_sox"}
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        return None
