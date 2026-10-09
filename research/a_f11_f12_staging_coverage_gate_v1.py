#!/usr/bin/env python3
"""Read-only F11/F12 staging coverage gate. No API, no writes, no production mutation."""
import json,sqlite3
from pathlib import Path
DB=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
F11=Path("/var/data/stock-alert/f11-staging/a_f11_staging_v1.json")
def main():
 if not DB.is_file() or not F11.is_file():raise SystemExit("STOP F11/F12 source missing")
 with sqlite3.connect(f"file:{DB}?mode=ro",uri=True) as conn:
  universe={str(r[0]) for r in conn.execute("SELECT DISTINCT symbol FROM daily_ohlcv")}
 data=json.loads(F11.read_text(encoding="utf-8"))
 rows=data.get("symbols",data)
 if not isinstance(rows,dict):raise SystemExit("STOP invalid F11 schema")
 def valid(s):
  x=rows.get(s)
  return isinstance(x,dict) and str(x.get("symbol",""))==s and all(str(x.get(k) or "").strip() for k in ("market","securityType","industry"))
 missing=sorted(s for s in universe if not valid(s))
 print(f"F11/F12 staging universe={len(universe)} valid={len(universe)-len(missing)} missing={len(missing)}")
 if missing:raise SystemExit("STOP F11/F12 missing or invalid: "+",".join(missing[:20]))
 print("PASS F11/F12 staging coverage | NO NETWORK | NO WRITES")
if __name__=="__main__":main()
