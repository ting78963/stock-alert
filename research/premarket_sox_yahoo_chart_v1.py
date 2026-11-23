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
        close = float(meta["regularMarketPrice"])
        prev = float(meta.get("chartPreviousClose") or meta["previousClose"])
        timestamp = int(meta["regularMarketTime"])
        if not all(isfinite(x) and x > 0 for x in (close, prev)) or timestamp <= 0:
            raise ValueError("invalid quote")
        from zoneinfo import ZoneInfo
        market_time = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(ZoneInfo("America/New_York"))
        # Never accept a quote before 16:00 US Eastern as a completed session close.
        if (market_time.hour, market_time.minute) < (16, 0):
            raise ValueError("not a completed session")
        return {"available": True, "source": "yahoo_chart_sox", "close_date": market_time.date().isoformat(),
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
