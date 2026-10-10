#!/usr/bin/env python3
"""Diagnose F10 cutoff zero for 1341; read-only, no network."""
import sqlite3,json,datetime as dt
from pathlib import Path
p=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
if not p.is_file():raise SystemExit("STOP: F10 DB missing")
con=sqlite3.connect("file:"+str(p.resolve())+"?mode=ro",uri=True)
try:
 con.execute("PRAGMA query_only=ON")
 rows=con.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",("1341","2026-10-10")).fetchall()[::-1]
 print("1341 | F10 09:30 ZERO CUTOFF DIAG | READ ONLY | NO API")
 print("days",len(rows))
 for day,full,raw in rows:
  pts=json.loads(raw);before=[(str(t),float(v)) for t,v in pts if str(t)<="09:30:00"]
  last=before[-1] if before else None
  first=pts[0] if pts else None
  print(day,"full",full,"points",len(pts),"first",first,"last_at_0930",last,"end",pts[-1] if pts else None)
 print("NOTE: if all last_at_0930 values are missing or zero, F10=0 is a legitimate cutoff-specific STOP, not DB corruption.")
finally:con.close()
