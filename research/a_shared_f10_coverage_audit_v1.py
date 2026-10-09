#!/usr/bin/env python3
"""Read-only coverage audit: session freshness and per-symbol F10 ten-day coverage."""
import sqlite3
from pathlib import Path
D=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
F=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
def ro(p):
    return sqlite3.connect(f"file:{p}?mode=ro",uri=True,timeout=5)
with ro(D) as d, ro(F) as f:
    last_d=d.execute("SELECT MAX(day) FROM daily_ohlcv").fetchone()[0]
    last_f=f.execute("SELECT MAX(day) FROM f10_day").fetchone()[0]
    dsyms={r[0] for r in d.execute("SELECT DISTINCT symbol FROM daily_ohlcv")}
    fsyms={r[0] for r in f.execute("SELECT DISTINCT symbol FROM f10_day")}
    daily_latest={r[0] for r in d.execute("SELECT DISTINCT symbol FROM daily_ohlcv WHERE day=?",(last_d,))}
    f10_latest={r[0] for r in f.execute("SELECT DISTINCT symbol FROM f10_day WHERE day=?",(last_f,))}
    f10_10={r[0] for r in f.execute("SELECT symbol FROM f10_day WHERE day<'2026-10-09' GROUP BY symbol HAVING COUNT(*)>=10")}
    status=d.execute("SELECT covered_through,COUNT(*) FROM fetch_status GROUP BY covered_through ORDER BY covered_through DESC LIMIT 10").fetchall()
    missing10=sorted(dsyms-f10_10)
    print("DAILY_LAST_DAY =",last_d,"COVERED_SYMBOLS =",len(daily_latest),"/",len(dsyms))
    print("F10_LAST_DAY =",last_f,"COVERED_SYMBOLS =",len(f10_latest),"/",len(fsyms))
    print("SYMBOL_SETS_MATCH =",dsyms==fsyms)
    print("F10_AT_LEAST_10_DAYS =",len(f10_10),"/",len(dsyms))
    print("F10_MISSING_10_COUNT =",len(missing10),"SAMPLE =",missing10[:20])
    print("DAILY_MISSING_LAST_COUNT =",len(dsyms-daily_latest),"SAMPLE =",sorted(dsyms-daily_latest)[:20])
    print("F10_MISSING_LAST_COUNT =",len(fsyms-f10_latest),"SAMPLE =",sorted(fsyms-f10_latest)[:20])
    print("DAILY_FETCH_STATUS_TOP =",status)
    print("AUDIT=READ_ONLY; HTTP=NONE; WRITES=NONE")
