#!/usr/bin/env python3
"""Read-only preflight for shared daily and F10 SQLite. No scanner, HTTP, writes."""
import os, sqlite3
from pathlib import Path

daily = Path(os.environ.get("A_SHARED_DAILY_DB", "/var/data/stock-alert/shared_history_stage_v1.sqlite3"))
f10 = Path(os.environ.get("PRODUCTION_STATE_DIR", "/var/data/stock-alert")) / "f10_baseline_v1.sqlite3"
def connect(p):
    if not p.is_file():
        print(f"MISSING {p}")
        return None
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)
for name, path in (("DAILY", daily), ("F10", f10)):
    print(f"{name}_PATH = {path}")
    db = connect(path)
    if db is None:
        print(f"{name}_RESULT = MISSING")
        continue
    try:
        print(f"{name}_INTEGRITY = {db.execute('PRAGMA quick_check').fetchone()[0]}")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        print(f"{name}_TABLES = {sorted(tables)}")
        table = "daily_ohlcv" if name == "DAILY" else "f10_day"
        if table not in tables:
            print(f"{name}_RESULT = STOP_MISSING_TABLE")
            continue
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
        print(f"{name}_COLUMNS = {cols}")
        if name == "DAILY":
            required = {"symbol","day","close","volume_zhang"}
            if not required.issubset(cols) or "fetch_status" not in tables:
                print("DAILY_RESULT = STOP_SCHEMA")
                continue
            print("DAILY_ROWS_SYMBOLS_DATES =", db.execute("SELECT COUNT(*),COUNT(DISTINCT symbol),MIN(day),MAX(day) FROM daily_ohlcv").fetchone())
            print("DAILY_1303 =", db.execute("SELECT COUNT(*),MAX(day) FROM daily_ohlcv WHERE symbol='1303'").fetchone())
            print("DAILY_1303_STATUS =", db.execute("SELECT covered_through FROM fetch_status WHERE symbol='1303'").fetchone())
        else:
            required = {"symbol","day","full","pts_json"}
            if not required.issubset(cols):
                print("F10_RESULT = STOP_SCHEMA")
                continue
            print("F10_ROWS_SYMBOLS_DATES =", db.execute("SELECT COUNT(*),COUNT(DISTINCT symbol),MIN(day),MAX(day) FROM f10_day").fetchone())
            print("F10_1303_LAST10 =", db.execute("SELECT day,full,length(pts_json) FROM f10_day WHERE symbol='1303' AND day<'2026-10-09' ORDER BY day DESC LIMIT 10").fetchall())
        print(f"{name}_RESULT = READ_ONLY_PASS")
    except sqlite3.Error as e:
        print(f"{name}_RESULT = STOP_SQLITE_{type(e).__name__}: {e}")
    finally:
        db.close()
print("HTTP=NONE; WRITES=NONE; PRODUCTION_CODE_UNCHANGED")
