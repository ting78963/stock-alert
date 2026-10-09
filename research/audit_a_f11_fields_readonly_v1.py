#!/usr/bin/env python3
"""Read-only F11 metadata audit: candidate relevance and cache validity.
Uses existing on-disk files only. No network, scanner, or writes.
"""
import json,sqlite3
from pathlib import Path
db=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
cache=Path("/var/data/stock-alert/a_f11_metadata_v1.json")
if not db.is_file():raise SystemExit("STOP: shared SQLite missing")
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
try:
    universe={str(x[0]) for x in con.execute("SELECT DISTINCT symbol FROM daily_ohlcv")}
finally:con.close()
if not cache.is_file():raise SystemExit("STOP: F11 cache missing")
raw=json.loads(cache.read_text(encoding="utf-8"))
entries=raw.get("symbols",raw)
if not isinstance(entries,dict):raise SystemExit("STOP: invalid F11 cache")
valid={str(k):v for k,v in entries.items() if isinstance(v,dict) and str(v.get("symbol") or "")==str(k)}
present=set(valid)&universe
missing=universe-present
print("UNIVERSE =",len(universe),"F11_PRESENT =",len(present),"F11_MISSING =",len(missing))
print("F11_FIELD_NAMES_SAMPLE =",sorted(set().union(*(set(v) for v in list(valid.values())[:30]))))
print("MISSING_FIRST_20 =",",".join(sorted(missing)[:20]))
print("IMPORTANT: missing F11 entries can trigger synchronous ticker HTTP only for A first-gate candidates")
print("NO REAL-TIME CANDIDATE SNAPSHOT; ACTUAL REQUEST COUNT AND LATENCY UNKNOWN")
print("READ_ONLY=YES; HTTP=NONE; A/B/LINE=NONE; PRODUCTION_WRITES=NONE")
