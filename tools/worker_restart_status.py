#!/usr/bin/env python3
"""Produce a local read-only Worker health snapshot, never trigger a restart.

The file remains on the Render worker's private disk. This does not publish
secrets or pretend GitHub Actions can access it. F15, live jobs and daily
restart attempt require independent authoritative integrations.
"""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
from zoneinfo import ZoneInfo

TPE = ZoneInfo("Asia/Taipei")
ROOT = Path("/var/data/stock-alert")
MIN_FREE_BYTES = 100 * 1024 * 1024

def snapshot(root=ROOT, now=None):
    now = now or dt.datetime.now(TPE)
    now = now.astimezone(TPE)
    day = now.date().isoformat()
    result = {
        "schema": "daily_maintenance_state_v2",
        "date": day,
        "stages": [],
        "line_sent": False,
        "line_accepted_at": None,
        "f15_complete": None,
        "active_trading_jobs": None,
        "restart_attempted": None,
        "disk_ok": False,
        "database_ok": False,
    }
    path = root / "daily_maintenance_state" / (day + ".json")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("schema") == "daily_maintenance_state_v2"
                and record.get("date") == day
                and isinstance(record.get("stages"), list)
                and all(isinstance(x, str) for x in record["stages"])):
            result["stages"] = record["stages"]
            result["line_sent"] = record.get("line_sent") is True
            result["line_accepted_at"] = record.get("line_accepted_at")
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    try:
        result["disk_ok"] = shutil.disk_usage(root).free >= MIN_FREE_BYTES
    except OSError:
        pass
    db = root / "shared_history_stage_v1.sqlite3"
    try:
        with sqlite3.connect("file:" + str(db) + "?mode=ro", uri=True, timeout=3) as conn:
            result["database_ok"] = conn.execute("PRAGMA quick_check(1)").fetchone()[0] == "ok"
    except (sqlite3.Error, OSError):
        pass
    return result

if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False, sort_keys=True))
