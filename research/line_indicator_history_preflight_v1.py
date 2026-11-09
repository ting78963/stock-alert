#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only preflight for LINE indicator migration. Never creates or writes DB files."""
import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = "/var/data/stock-alert/shared_history_stage_v1.sqlite3"
REQUIRED = {"symbol", "day", "open", "high", "low", "close"}

def audit(db_path, symbol, asof, min_days=90):
    path = Path(db_path)
    if not path.is_file():
        return {"status": "BLOCKED", "reason": "DB_NOT_FOUND", "path": str(path)}
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            cols = {r[1] for r in db.execute("PRAGMA table_info(daily_ohlcv)")}
            if not REQUIRED <= cols:
                return {"status": "BLOCKED", "reason": "MISSING_COLUMNS", "columns": sorted(cols)}
            rows = db.execute(
                "SELECT day,open,high,low,close FROM daily_ohlcv "
                "WHERE symbol=? AND day<? ORDER BY day DESC LIMIT ?",
                (symbol, asof, min_days),
            ).fetchall()
            if len(rows) < min_days:
                return {"status": "BLOCKED", "reason": "INSUFFICIENT_DAYS",
                        "symbol": symbol, "rows": len(rows), "required": min_days}
            if any(any(v is None or not isinstance(v, (int, float)) or v <= 0 for v in r[1:])
                   or r[2] < max(r[1], r[4])
                   or r[3] > min(r[1], r[4]) for r in rows):
                return {"status": "BLOCKED", "reason": "INVALID_OHLC", "symbol": symbol}
            return {"status": "PASS", "symbol": symbol, "rows": len(rows),
                    "first_day": rows[-1][0], "last_day": rows[0][0],
                    "note": "Completed historical days only (strictly before asof); live price and source parity still require checks."}
    except (sqlite3.Error, OSError) as exc:
        return {"status": "BLOCKED", "reason": type(exc).__name__, "detail": str(exc)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--symbol", required=True)
    p.add_argument("--asof", required=True, help="YYYY-MM-DD; no future data")
    args = p.parse_args()
    result = audit(args.db, args.symbol, args.asof)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)

if __name__ == "__main__":
    main()
