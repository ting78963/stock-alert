# -*- coding: utf-8 -*-
"""TAIEX IX0001 daily close store using the SAME Fugle historical API as F15 stocks."""
from __future__ import annotations
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import urllib.parse
import urllib.request
from taiex_market_history_v1 import normalize_daily, snapshot

FUGLE_URL = "https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/IX0001"
TPE = ZoneInfo("Asia/Taipei")
STORE = Path(os.getenv("TAIEX_HISTORY_PATH", "/var/data/stock-alert/f15_market/taiex_daily.json"))


def date_ranges(start, end):
    """Use half-year chunks: Fugle rejects any query spanning a full year."""
    d = start
    while d <= end:
        last = min(end, d + timedelta(days=179))
        yield d, last
        d = last + timedelta(days=1)


def fetch_range(start, end, session=None, api_key=None):
    key = api_key or os.getenv("FUGLE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FUGLE_API_KEY missing")
    params = urllib.parse.urlencode({"from":start.isoformat(),"to":end.isoformat(),"timeframe":"D","fields":"close","sort":"asc"})
    url = FUGLE_URL + "?" + params
    request = urllib.request.Request(url,headers={"X-API-KEY":key,"Accept":"application/json"})
    if session is not None:
        payload = session(request)
    else:
        with urllib.request.urlopen(request,timeout=20) as response:
            payload = json.load(response)
    if payload.get("symbol") != "IX0001" or str(payload.get("timeframe")) != "D" or not isinstance(payload.get("data"),list):
        raise ValueError("Fugle IX0001 response identity/schema mismatch")
    rows = normalize_daily([{"date": r["date"], "close": r["close"]} for r in payload["data"]])
    if any(not (start.isoformat() <= r["date"] <= end.isoformat()) for r in rows):
        raise ValueError("Fugle IX0001 returned out-of-range dates")
    return rows


def read_store(path=STORE):
    if not path.exists():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("schema") != "taiex_daily_v1":
        raise ValueError("TAIEX history schema mismatch")
    return normalize_daily(obj["rows"])


def write_store(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"schema": "taiex_daily_v1", "rows": normalize_daily(rows)}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def update(as_of=None, path=STORE, session=None, api_key=None, max_chunks=2):
    today = as_of or datetime.now(TPE).date()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    existing = read_store(path)
    start = date(today.year - 3, today.month, 1) if not existing else date.fromisoformat(existing[-1]["date"]) + timedelta(days=1)
    merged = {r["date"]: r for r in existing}
    fetched = 0
    for index, (a, b) in enumerate(date_ranges(start, today)):
        if index >= max_chunks:
            break
        new_rows = fetch_range(a, b, session=session, api_key=api_key)
        for row in new_rows:
            merged[row["date"]] = row
            fetched += 1
        # Checkpoint successful chunks so bootstrap can resume after network failures.
        write_store(path, merged.values())
    rows = normalize_daily(merged.values())
    if len(rows) < len(existing):
        raise RuntimeError("TAIEX history unexpectedly shrank")
    report_as_of = today + timedelta(days=1) if rows and rows[-1]["date"] == today.isoformat() else today
    return {"stored": len(rows), "fetched_rows": fetched, "latest": rows[-1]["date"] if rows else None, "snapshot": snapshot(rows, report_as_of.isoformat())}


if __name__ == "__main__":
    print(json.dumps(update(), ensure_ascii=False, indent=2))
