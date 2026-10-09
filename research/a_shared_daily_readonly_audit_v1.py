#!/usr/bin/env python3
"""Read-only offline adapter/audit for A's shared daily history. No network calls.
Research only: DOES NOT alter production A or its historical semantics.
"""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = "/var/data/stock-alert/shared_history_stage_v1.sqlite3"

class HistoryNotReady(Exception):
    pass

def read_daily(db_path, symbol, snapshot_date):
    """Match A's original inclusive 170-calendar-day range, strictly before D0."""
    snap = dt.date.fromisoformat(snapshot_date)
    to_day = snap - dt.timedelta(days=1)
    from_day = to_day - dt.timedelta(days=170)
    uri = "file:" + str(Path(db_path).resolve()) + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as db:
        check = db.execute(
            "SELECT covered_through FROM fetch_status WHERE symbol=?", (symbol,)
        ).fetchone()
        if check is None or not check[0] or check[0] < to_day.isoformat():
            raise HistoryNotReady(
                f"{symbol}: fetch_status does not cover {to_day}; status={check}"
            )
        rows = db.execute(
            """SELECT day,close,volume_zhang FROM daily_ohlcv
               WHERE symbol=? AND day>=? AND day<=? ORDER BY day""",
            (symbol, from_day.isoformat(), to_day.isoformat())
        ).fetchall()
    if not rows:
        raise HistoryNotReady(f"{symbol}: no daily rows in requested range")
    out = []
    for day, close, vol in rows:
        if not (from_day.isoformat() <= day < snapshot_date):
            raise AssertionError(f"future/out-of-range data: {symbol} {day}")
        if close is None or vol is None or float(close) <= 0 or float(vol) < 0:
            raise HistoryNotReady(f"{symbol}: invalid daily row {day}")
        out.append({"date": day, "close": float(close), "volume_zhang": float(vol)})
    return out

def audit(db_path, snapshot_date):
    uri = "file:" + str(Path(db_path).resolve()) + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        symbols = [x[0] for x in db.execute("SELECT DISTINCT symbol FROM daily_ohlcv ORDER BY symbol")]
    ready = 0
    not_ready = []
    sizes = []
    for symbol in symbols:
        try:
            rows = read_daily(db_path, symbol, snapshot_date)
            ready += 1
            sizes.append(len(rows))
        except HistoryNotReady as exc:
            not_ready.append(str(exc))
    result = {
        "snapshot_date": snapshot_date, "stocks": len(symbols),
        "local_ready": ready, "not_ready": len(not_ready),
        "min_rows": min(sizes) if sizes else None,
        "max_rows": max(sizes) if sizes else None,
        "not_ready_examples": not_ready[:20],
        "network_requests": 0,
        "note": "Coverage is checked by fetch_status watermark; old-vs-new data parity NOT yet verified."
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not not_ready else 2

def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "test.sqlite3")
        with sqlite3.connect(path) as db:
            db.executescript("""CREATE TABLE daily_ohlcv(symbol TEXT,day TEXT,open REAL,high REAL,low REAL,close REAL,volume_zhang REAL);
            CREATE TABLE fetch_status(symbol TEXT,covered_through TEXT,last_success_utc TEXT);""")
            db.execute("INSERT INTO daily_ohlcv VALUES ('1101','2026-10-08',1,1,1,10,20)")
            db.execute("INSERT INTO fetch_status VALUES ('1101','2026-10-11','x')")
        assert read_daily(path,"1101","2026-10-12") == [
            {"date":"2026-10-08","close":10.0,"volume_zhang":20.0}]
        try:
            read_daily(path,"1101","2026-10-13")
            raise AssertionError("expected not-ready")
        except HistoryNotReady:
            pass
    print("PASS: offline reader, date exclusion, watermark guard, zero network")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--snapshot-date", default="2026-10-12")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test()
    else:
        raise SystemExit(audit(a.db, a.snapshot_date))
