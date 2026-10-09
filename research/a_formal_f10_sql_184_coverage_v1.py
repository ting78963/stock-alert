#!/usr/bin/env python3
"""Audit F15 historical F10 coverage using EXACT production A SQLite lookup.
READ ONLY; no API; no modifications; NOT a handoff-performance replay.
"""
import json, sqlite3, collections, math
from pathlib import Path
P=Path("/var/data/stock-alert")
root=P/"f15_eod/trajectory_v1"
db=P/"f10_baseline_v1.sqlite3"
files=sorted(x for x in root.glob("20??-??-??/*.json") if x.name!="manifest.json")
if not files or not db.is_file(): raise SystemExit("AUDIT STOP: F15 or F10 missing")
con=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True)
try:
  assert con.execute("PRAGMA query_only").fetchone()[0] in (0,1)
  print("FORMAL A F10 SQL COVERAGE | READ ONLY | NO API | NO WRITES")
  print("F15 files",len(files),"F10 rows",con.execute("SELECT count(*) FROM f10_day").fetchone()[0])
  stats=collections.Counter(); days=collections.defaultdict(collections.Counter); cls=collections.defaultdict(collections.Counter)
  failures=[]; identities=set()
  for f in files:
    try:
      j=json.loads(f.read_text()); i=j["identity"]
      d=str(i["date"]); s=str(i["stock_id"]); c=str(i["signal_class"]); t=str(i["recognition_time"])
      assert d==f.parent.name and c in ("A","B","C","P1")
      key=(d,s,c,t); assert key not in identities; identities.add(key)
      assert isinstance(j["trajectory_raw_1m"],list) and j["trajectory_raw_1m"]
      # Exact SQL from fugle_a_scanner_v2_4.py, not an invented calendar.
      rows=con.execute("""SELECT day, full, pts_json FROM f10_day
                         WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10""",(s,d)).fetchall()
      status="A_SQL_10_ROWS" if len(rows)==10 else "A_SQL_LT10_ROWS"
      if rows:
        seen=set()
        for rd,full,raw in rows:
          assert rd<d and rd not in seen; seen.add(rd)
          assert math.isfinite(float(full)) and float(full)>0
          pts=json.loads(raw)
          assert isinstance(pts,list) and pts
          prev=-1.0; seen_tm=set()
          for tm,v in pts:
            assert str(tm) not in seen_tm; seen_tm.add(str(tm))
            v=float(v); assert math.isfinite(v) and v>=prev; prev=v
          assert abs(prev-float(full))<=1e-9
      stats[status]+=1; days[d][status]+=1; cls[c][status]+=1
      if status!="A_SQL_10_ROWS": failures.append((d,s,c,len(rows),",".join(x[0] for x in rows)))
    except Exception as e: raise SystemExit("AUDIT STOP: "+str(f)+" "+repr(e))
  print("IDENTITY PASS",len(identities))
  print("COUNTS",dict(stats))
  print("BY DAY")
  for d in sorted(days): print(d,dict(days[d]))
  print("BY CLASS")
  for c in sorted(cls): print(c,dict(cls[c]))
  print("LESS THAN 10 ROWS: date stock class count available_dates")
  for row in failures: print(*row,sep=" | ")
  print("LIMIT: This checks A's F10 SQL and stored curve integrity, not prior-time availability.")
  print("LIMIT: Fewer than 10 rows does NOT imply an API call: cache, daily_history and fallback rules also apply.")
  print("LIMIT: No 800/1000 performance or B workload is inferred.")
finally: con.close()
