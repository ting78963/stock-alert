#!/usr/bin/env python3
"""Read-only F11/VCP coverage audit. No network, database writes or service restart."""
import json
import os
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(os.environ.get("A_STOCK_ROOT", "/var/data/stock-alert"))
META = ROOT / "a_f11_metadata_v1.json"
DB = Path(os.environ.get("A_SHARED_DAILY_DB", str(ROOT / "shared_history_stage_v1.sqlite3")))
EXCLUDED = {"02", "09", "14", "15", "16", "17", "18", "22", "32"}

def main():
    metadata = json.loads(META.read_text(encoding="utf-8"))
    records = metadata.get("symbols", {})
    staging_enabled = os.environ.get("A_F11_OFFLINE_STAGING", "") == "1"
    if staging_enabled:
        staging_file = ROOT / "f11-staging" / "a_f11_staging_v1.json"
        staging = json.loads(staging_file.read_text(encoding="utf-8"))
        records = staging.get("symbols", staging.get("records", {}))
    if not isinstance(records, dict):
        raise ValueError("F11 symbols must be a dict")
    required = os.environ.get("A_LAST_COMPLETED_SESSION", "").strip()
    snapshot = os.environ.get("A_AUDIT_SNAPSHOT_DATE", datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat())
    target = (date.fromisoformat(snapshot) - timedelta(days=1)).isoformat()
    counts = Counter()
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conn:
        symbols = [str(row[0]) for row in conn.execute("SELECT DISTINCT symbol FROM daily_ohlcv")]
        for symbol in symbols:
            meta = records.get(symbol)
            if not isinstance(meta, dict) or str(meta.get("symbol", "")) != symbol:
                counts["f11_missing_or_invalid"] += 1
            elif (str(meta.get("market") or "") == "ESB"
                  or (str(meta.get("securityType") or "") not in ("", "01"))
                  or str(meta.get("industry") or "") in EXCLUDED):
                counts["f11_excluded"] += 1
            else:
                counts["f11_eligible"] += 1
            status = conn.execute("SELECT covered_through FROM fetch_status WHERE symbol=?", (symbol,)).fetchone()
            if not required:
                counts["session_env_missing"] += 1
            elif not status or not status[0] or str(status[0])[:10] < required:
                counts["coverage_not_ready"] += 1
            else:
                counts["coverage_ready"] += 1
            rows = conn.execute(
                "SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day<? AND day>=? ORDER BY day",
                (symbol, snapshot, (date.fromisoformat(snapshot)-timedelta(days=171)).isoformat())
            ).fetchall()
            if len(rows) >= 60 and all(c is not None and v is not None and c > 0 and v >= 0 for _,c,v in rows):
                counts["prior_60_bars_ready"] += 1
            else:
                counts["prior_60_bars_missing"] += 1
    print(json.dumps({
        "snapshot_date": snapshot, "last_completed_session": required or None,
        "target_previous_calendar_day": target, "database_symbols": len(symbols),
        "f11_file_symbols": len(records), "f11_offline_staging_enabled": staging_enabled, "counts": dict(sorted(counts.items())),
        "note": "Coverage counters are independent; VCP still requires all gates. No files modified."
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
