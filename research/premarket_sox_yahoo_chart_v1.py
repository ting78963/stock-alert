"""Read-only Yahoo Chart SOX close source for the 08:55 premarket report.

Never reports an undated quote as the previous completed US session.
No scheduling, LINE, database, or scanner side effects.
"""
from datetime import datetime, timezone
from math import isfinite
from urllib.request import Request, urlopen
import json

URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ESOX?range=5d&interval=1d"


def parse_sox_chart(payload):
    try:
        item = payload["chart"]["result"][0]
        meta = item["meta"]
        if meta.get("symbol") != "^SOX":
            raise ValueError("wrong symbol")
        from zoneinfo import ZoneInfo
        us = ZoneInfo("America/New_York")
        timestamps = item["timestamp"]
        closes = item["indicators"]["quote"][0]["close"]
        completed = []
        for ts, raw in zip(timestamps, closes):
            if raw is None:
                continue
            day = datetime.fromtimestamp(int(ts), timezone.utc).astimezone(us).date()
            # Exclude today's session unless the US market has already closed.
            now_us = datetime.now(timezone.utc).astimezone(us)
            if day >= now_us.date() and (now_us.hour, now_us.minute) < (16, 0):
                continue
            value = float(raw)
            if isfinite(value) and value > 0:
                completed.append((day, value))
        if len(completed) < 2:
            raise ValueError("insufficient completed daily bars")
        day, close = completed[-1]
        prev = completed[-2][1]
        return {"available": True, "source": "yahoo_chart_sox", "close_date": day.isoformat(),
                "close": round(close, 3), "previous_close": round(prev, 3),
                "change_pct": round((close / prev - 1) * 100, 2)}

    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
        return {"available": False, "reason": str(exc)}


def fetch_sox_chart(opener=urlopen, timeout=8):
    request = Request(URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with opener(request, timeout=timeout) as response:
            body = response.read(200_001)
        if len(body) > 200_000:
            return {"available": False, "reason": "response_too_large"}
        return parse_sox_chart(json.loads(body))
    except (OSError, ValueError, UnicodeError) as exc:
        return {"available": False, "reason": type(exc).__name__}
