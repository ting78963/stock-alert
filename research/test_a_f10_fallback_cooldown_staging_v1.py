#!/usr/bin/env python3
"""F10 repeated failure: same missing day must not cause a second API request."""
import os,sys,importlib.util,sqlite3
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
p=Path("/tmp/a_f10_incremental_staging.py")
if not p.is_file():raise SystemExit("STOP staged scanner missing")
spec=importlib.util.spec_from_file_location("a_f10_retry_check",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
os.environ.update(PRODUCTION_STATE_DIR="/var/data/stock-alert",A_F10_FALLBACK_MAX_DAYS="2",A_F10_FALLBACK_COOLDOWN_SECONDS="1800")
db=sqlite3.connect("file:/var/data/stock-alert/f10_baseline_v1.sqlite3?mode=ro",uri=True)
rows=db.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",("1303","2026-10-09")).fetchall();db.close()
assert len(rows)==10
missing=rows[0][0];dates=sorted(r[0] for r in rows)
class Cursor:
 def fetchall(self):return [r for r in rows if r[0]!=missing]
class Conn:
 def execute(self,*a,**kw):return Cursor()
 def close(self):pass
a=m.FugleAdapter("OFFLINE");a.history_cache={}
a.daily_history=lambda *args:[m.DailyBar(d,100,1000) for d in dates]
calls=[]
def api(url):
 calls.append(url)
 raise RuntimeError("simulated temporary Fugle outage")
a.historical_json=api
dt=datetime(2026,10,9,10,30,tzinfo=ZoneInfo("Asia/Taipei"))
with patch.object(m.sqlite3,"connect",return_value=Conn()),patch.object(m,"save_json_atomic",side_effect=AssertionError("write forbidden")):
 for i in range(2):
  try:a.estimated_vr5_parts("1303","2026-10-09",dt)
  except (RuntimeError,m.AuditStop) as e:print(f"attempt {i+1}: {type(e).__name__}: {e}")
  else:raise AssertionError("Expected failed fetch or cooldown")
assert len(calls)==1,("repeated API burst",len(calls))
print("PASS first missing day fetch=1; immediate retry fetch=0")
print("PASS no real HTTP, no writes")
print("RESULT = PASS")
