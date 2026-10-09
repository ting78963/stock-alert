#!/usr/bin/env python3
"""Read-only F11 three-field coverage audit; no external requests."""
import json,sqlite3,collections
from pathlib import Path
db=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
f=Path("/var/data/stock-alert/a_f11_metadata_v1.json")
if not db.is_file() or not f.is_file():raise SystemExit("STOP: input missing")
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
try:universe={str(r[0]) for r in con.execute("SELECT DISTINCT symbol FROM daily_ohlcv")}
finally:con.close()
raw=json.loads(f.read_text(encoding="utf-8"))
rows=raw.get("symbols",raw)
assert isinstance(rows,dict)
valid={k:v for k,v in rows.items() if k in universe and isinstance(v,dict) and str(v.get("symbol") or "")==k}
print("UNIVERSE =",len(universe),"F11_VALID =",len(valid),"F11_MISSING =",len(universe)-len(valid))
for field in ("market","securityType","industry"):
    counts=collections.Counter(str(v.get(field) or "<empty>") for v in valid.values())
    print(field,"TOP_VALUES =",counts.most_common(12),"EMPTY =",counts.get("<empty>",0))
print("META_OK_INPUTS = market, securityType, industry")
print("WARNING: existing meta_ok permits empty fields; this audit does not change that")
print("READ_ONLY=YES; HTTP=NONE; A/B/LINE=NONE; PRODUCTION_WRITES=NONE")
