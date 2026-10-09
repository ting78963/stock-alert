#!/usr/bin/env python3
"""F11 gap plan, read only. No API and no file writes."""
import json,sqlite3
from pathlib import Path
db=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
cache=Path("/var/data/stock-alert/a_f11_metadata_v1.json")
if not db.is_file() or not cache.is_file():raise SystemExit("STOP: required data absent")
conn=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
try: universe={str(r[0]) for r in conn.execute("SELECT DISTINCT symbol FROM daily_ohlcv")}
finally:conn.close()
obj=json.loads(cache.read_text(encoding="utf-8"))
rows=obj.get("symbols",obj)
if not isinstance(rows,dict):raise SystemExit("STOP: invalid cache")
present={s for s,v in rows.items() if s in universe and isinstance(v,dict) and str(v.get("symbol") or "")==s and all(str(v.get(k) or "") for k in ("market","securityType","industry"))}
missing=sorted(universe-present)
print("F11 CACHE REUSE =",len(present))
print("F11 NEEDS FETCH =",len(missing))
print("F11 MISSING FIRST 20 =",",".join(missing[:20]))
print("DRY-RUN BATCH SIZES:")
for n in (20,50,100):
    batches=(len(missing)+n-1)//n
    print(" batch",n,":",batches,"batches")
print("PROPOSED RULES: premarket only; rate-limit; atomic checkpoint; validate identity and all 3 fields; no overwrite of valid cache")
print("CAUTION: missing metadata must not be treated as eligible; no synchronous ticker API in A scan after future change")
print("NO FETCH EXECUTED; NO API SPEED ASSUMED")
print("READ_ONLY=YES; HTTP=NONE; A/B/LINE=NONE; PRODUCTION_WRITES=NONE")
