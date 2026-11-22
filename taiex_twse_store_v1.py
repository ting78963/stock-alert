# -*- coding: utf-8 -*-
"""Independent TAIEX daily-close store for future F15 maintenance integration.

Source: TWSE exchangeReport/FMTQIK monthly daily index series.
No background threads, no LINE, no modifications to A/B or F15 signal archives.
"""
from __future__ import annotations
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from taiex_market_history_v1 import normalize_daily, snapshot

TWSE_URL = "https://www.twse.com.tw/exchangeReport/FMTQIK"
TPE = ZoneInfo("Asia/Taipei")
STORE = Path(os.getenv("TAIEX_HISTORY_PATH", "/var/data/stock-alert/f15_market/taiex_daily.json"))


def month_starts(start, end):
    d = date(start.year, start.month, 1)
    while d <= end:
        yield d
        d = date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)


def parse_roc_date(value):
    parts = str(value).strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid TWSE ROC date: {value!r}")
    return date(int(parts[0]) + 1911, int(parts[1]), int(parts[2])).isoformat()


def parse_month(payload):
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        raise ValueError("TWSE FMTQIK response not OK")
    fields = payload.get("fields")
    rows = payload.get("data")
    if not isinstance(fields, list) or not isinstance(rows, list):
        raise ValueError("TWSE FMTQIK schema missing fields/data")
    # Match by column label, never assume the index is always at a fixed position.
    label = "發行量加權股價指數"
    matches = [i for i, f in enumerate(fields) if str(f).strip() == label]
    if len(matches) != 1:
        raise ValueError("TWSE FMTQIK index column unavailable")
    col = matches[0]
    result = []
    for row in rows:
        if not isinstance(row, list) or len(row) <= col:
            raise ValueError("TWSE FMTQIK row malformed")
        result.append({"date": parse_roc_date(row[0]), "close": float(str(row[col]).replace(",", ""))})
    return normalize_daily(result)


def fetch_month(month, session=None):
    client = session or requests
    response = client.get(TWSE_URL, params={"response": "json", "date": month.strftime("%Y%m%d")}, timeout=20)
    response.raise_for_status()
    return parse_month(response.json())


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


def update(as_of=None, path=STORE, session=None):
    """Manual or scheduled invocation after official close; never silently drop existing rows."""
    today = as_of or datetime.now(TPE).date()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    existing = read_store(path)
    # Initial bootstrap: 30 months gives margin above 100 complete trading weeks.
    start = date(today.year - 3, today.month, 1) if not existing else date.fromisoformat(existing[-1]["date"]).replace(day=1)
    if not existing:
        # 36 months of calendar data, deliberately conservative.
        start = date(today.year - 3, today.month, 1)
    merged = {r["date"]: r for r in existing}
    fetched = 0
    for month in month_starts(start, today):
        for row in fetch_month(month, session):
            if row["date"] <= today.isoformat():
                merged[row["date"]] = row
                fetched += 1
    rows = normalize_daily(merged.values())
    if len(rows) < len(existing):
        raise RuntimeError("TAIEX history unexpectedly shrank")
    write_store(path, rows)
    return {"stored": len(rows), "fetched_rows": fetched, "latest": rows[-1]["date"] if rows else None, "snapshot": snapshot(rows, (today + timedelta(days=1)).isoformat() if rows and rows[-1]["date"] == today.isoformat() else today.isoformat())}


if __name__ == "__main__":
    print(json.dumps(update(), ensure_ascii=False, indent=2))
