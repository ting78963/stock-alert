#!/usr/bin/env python3
"""Read-only real DB test: last ten rows, no fabricated dates, day exclusion."""
import sqlite3
from pathlib import Path
D=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
F=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
snap="2026-10-09"
symbols=("1303","2323","6236","2073")
def ro(path): return sqlite3.connect(f"file:{path}?mode=ro",uri=True,timeout=5)
with ro(D) as d,ro(F) as f:
    for sym in symbols:
        ds=[r[0] for r in d.execute("SELECT day FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(sym,snap))]
        fs=[r[0] for r in f.execute("SELECT day FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(sym,snap))]
        ok=len(ds)==len(fs)==10 and ds==fs and len(set(ds))==10 and all(x<snap for x in ds)
        print(f"{sym}: DAILY10={len(ds)} F10={len(fs)} LAST={ds[0] if ds else '-'} MATCH={ok}")
        if not ok: raise SystemExit(f"STOP: identity/coverage mismatch for {sym}")
    print("TEN_VALID_RECORDED_DAYS = PASS (four sample symbols)")
    print("NO_TODAY_LEAKAGE = PASS")
    print("NO_FILLING_MISSING_DATES = PASS (source rows)")
    print("HTTP=0; WRITES=0")
