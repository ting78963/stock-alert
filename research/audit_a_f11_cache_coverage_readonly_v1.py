#!/usr/bin/env python3
"""Read-only F11 metadata cache coverage audit. No scanner import or HTTP."""
import json,sqlite3
from pathlib import Path
db=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
cache=Path("/var/data/stock-alert/a_f11_metadata_v1.json")
if not db.is_file():
    raise SystemExit("STOP: shared history SQLite missing")
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
try:
    symbols={str(r[0]) for r in con.execute("SELECT DISTINCT symbol FROM daily_ohlcv")}
finally:con.close()
print("SQLITE_STOCKS =",len(symbols))
if not cache.is_file():
    print("F11_CACHE = MISSING; ticker may require API on first candidate")
    raise SystemExit(0)
d=json.loads(cache.read_text(encoding="utf-8"))
if not isinstance(d,dict):
    raise SystemExit("STOP: malformed F11 cache root")
rows=d.get("symbols",d)
if not isinstance(rows,dict):
    raise SystemExit("STOP: malformed F11 symbols")
valid={str(k) for k,v in rows.items() if isinstance(v,dict) and str(v.get("symbol") or "")==str(k)}
overlap=valid&symbols
missing=symbols-valid
print("F11_CACHE_ENTRIES =",len(rows))
print("F11_VALID_IDENTITIES =",len(valid))
print("SQLITE_F11_OVERLAP =",len(overlap))
print("SQLITE_F11_MISSING =",len(missing))
print("MISSING_EXAMPLES =",",".join(sorted(missing)[:15]))
print("NOTE: this is universe-level coverage, NOT today's candidate count")
print("READ_ONLY=YES; HTTP=NONE; REAL_A_B_LINE=NONE")
