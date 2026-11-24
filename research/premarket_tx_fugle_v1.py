"""One-shot TX quote; no scanner, storage or LINE side effects."""
import json
import os
import re
from urllib.parse import urlencode
from datetime import datetime, time, timezone, timedelta
from math import isfinite
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TPE = ZoneInfo("Asia/Taipei")
URL = "https://api.fugle.tw/marketdata/v1.0/futopt/intraday/quote/TXF1%21"

def parse_tx(payload, report_at, previous_day_close=None):
    """Previous day-session close must be independently verified for this contract."""
    try:
        now = report_at.astimezone(TPE)
        symbol = payload["symbol"]
        if not isinstance(symbol, str) or not symbol.startswith("TXF"):
            return None
        if payload["date"] != now.date().isoformat():
            return None
        trade = payload["lastTrade"]
        raw = trade["time"]
        if isinstance(raw, (int, float)):
            stamp = datetime.fromtimestamp(raw / 1_000_000, timezone.utc)
        else:
            stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                return None
        local = stamp.astimezone(TPE)
        if local.date() != now.date() or not time(8,45) <= local.time() <= time(13,45):
            return None
        if not -30 <= (now-local).total_seconds() <= 180:
            return None
        price = float(trade["price"])
        if not isfinite(price) or price <= 0:
            return None
        change = None
        if previous_day_close is not None and previous_day_close.get("symbol") == symbol and previous_day_close.get("session") == "day":
            prev = float(previous_day_close["close"])
            if isfinite(prev) and prev > 0 and previous_day_close["date"] < now.date().isoformat():
                change = f"{price-prev:+,.0f} ({(price/prev-1)*100:+.2f}%)"
        return dict(value=f"{price:,.0f}", change=change, quoted_at=stamp.isoformat(), source="fugle", session="day", symbol=symbol)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError):
        return None

def fetch_tx_quote(report_at, previous_day_close=None, opener=urlopen, api_key=None):
    key = api_key or os.getenv("FUGLE_API_KEY", "").strip()
    if not key:
        return None
    try:
        req = Request(URL, headers={"X-API-KEY":key,"Accept":"application/json"})
        with opener(req, timeout=8) as response:
            body = response.read(200001)
        if len(body)>200000:
            return None
        payload = json.loads(body)
        quote = parse_tx(payload, report_at, previous_day_close)
        if quote is None or previous_day_close is not None:
            return quote
        try:
            prev = fetch_previous_close(quote["symbol"], report_at, opener, key)
            return parse_tx(payload, report_at, prev)
        except (OSError, ValueError, TypeError, KeyError):
            return quote
    except (OSError, ValueError):
        return None


def fetch_previous_close(symbol, report_at, opener, key):
    match = re.fullmatch(r"TXF([A-L])(\d)", symbol)
    if not match:
        return None
    day = report_at.astimezone(TPE).date()
    month = ord(match[1]) - ord("A") + 1
    year = next((y for y in (day.year, day.year+1) if y % 10 == int(match[2])), None)
    if year is None:
        return None
    contract = f"{year}{month:02d}"
    params = urlencode({"contractMonth":contract,"session":"regular","timeframe":"D","fields":"close","from":(day-timedelta(days=14)).isoformat(),"to":(day-timedelta(days=1)).isoformat(),"sort":"desc"})
    req = Request("https://api.fugle.tw/marketdata/v1.0/futopt/historical/candles/TXF?"+params,headers={"X-API-KEY":key,"Accept":"application/json"})
    with opener(req,timeout=8) as response:
        body=response.read(200001)
    if len(body)>200000:
        return None
    obj=json.loads(body)
    if obj.get("product")!="TXF" or obj.get("contractMonth")!=contract or obj.get("session")!="REGULAR" or obj.get("timeframe")!="D":
        return None
    rows=[r for r in obj["data"] if r.get("contractMonth")==contract and (day-timedelta(days=14)).isoformat()<=r["date"]<day.isoformat()]
    if not rows:
        return None
    row=max(rows,key=lambda r:r["date"])
    return dict(symbol=symbol,session="day",date=row["date"],close=row["close"])
