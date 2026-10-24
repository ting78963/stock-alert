#!/usr/bin/env python3
"""Read-only Oct 22 VCP input coverage, not a VCP signal replay."""
import json,sqlite3
from pathlib import Path
from collections import Counter
ROOT=Path("/var/data/stock-alert");DAY="2026-10-22"
files=sorted((ROOT/"f15_eod/trajectory_v1"/DAY).glob("*.json"))
db=ROOT/"shared_history_stage_v1.sqlite3"
if not db.exists():raise SystemExit("STOP: daily DB missing")
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
print("symbol,first_800,prior_daily_count,prior5_avg_lots,raw_vr5_at_800,daily_ready,metadata_verified,vcp_signal")
cnt=Counter()
for p in files:
 if p.name=="manifest.json":continue
 d=json.loads(p.read_text(encoding="utf-8"))
 sym=str(d["identity"]["stock_id"])
 bars=sorted(d.get("trajectory_raw_1m",[]),key=lambda b:str(b.get("minute","")))
 first=next((b for b in bars if float(b.get("cum_volume",0))>=800),None)
 rows=con.execute("SELECT day,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 60",(sym,DAY)).fetchall()
 ready=len(rows)>=60 and len({x[0] for x in rows})==len(rows)
 avg=sum(float(x[1]) for x in rows[:5])/5 if len(rows)>=5 else None
 vol=float(first["cum_volume"]) if first else None
 vr=vol/avg if vol is not None and avg and avg>0 else None
 cnt["800_reached" if first else "below_800"]+=1
 cnt["daily_ready" if ready else "daily_not_ready"]+=1
 print(f"{sym},{str(first.get('minute'))[:5] if first else ''},{len(rows)},{round(avg,2) if avg else ''},{round(vr,3) if vr is not None else ''},{ready},UNKNOWN,NOT_TESTED")
con.close()
print("SUMMARY",json.dumps({"date":DAY,"counts":dict(cnt),"warning":"Daily bars and 800-lot tracking prerequisites only. Metadata and VCP state-machine not tested; not confirmed VCP signals. Read-only; no LINE."},ensure_ascii=False))
