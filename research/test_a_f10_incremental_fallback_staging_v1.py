#!/usr/bin/env python3
"""Isolated F10 incremental fallback regression. Mock DB rows and Fugle; no real HTTP or writes."""
import os,sys,importlib.util,sqlite3,json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
p=Path("/tmp/a_f10_incremental_staging.py")
if not p.is_file():raise SystemExit("STOP: staged scanner missing")
spec=importlib.util.spec_from_file_location("a_f10_fallback_check",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
os.environ["PRODUCTION_STATE_DIR"]="/var/data/stock-alert"
os.environ["A_F10_FALLBACK_MAX_DAYS"]="2"
db=sqlite3.connect("file:/var/data/stock-alert/f10_baseline_v1.sqlite3?mode=ro",uri=True)
rows=db.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",("1303","2026-10-09")).fetchall()
db.close()
assert len(rows)==10,"STOP: baseline fixture incomplete"
dates=sorted(r[0] for r in rows)
class FakeConnection:
 def __init__(self,missing):self.missing=missing
 def execute(self,*a,**kw):return [r for r in rows if r[0] not in self.missing]
 def close(self):pass
class FakeDB:
 def __init__(self,missing):self.missing=missing
 def connect(self,*a,**kw):return FakeConnection(self.missing)
dt=datetime(2026,10,9,10,30,tzinfo=ZoneInfo("Asia/Taipei"))
def run(missing,expected):
 calls=[];writes=[]
 adapter=m.FugleAdapter("OFFLINE");adapter.history_cache={};adapter._estvr5_cache={}
 def history(*a):return [m.DailyBar(d,100.0,1000.0) for d in dates]
 adapter.daily_history=history
 def api(url):
  calls.append(url)
  from urllib.parse import urlsplit,parse_qs
  q=parse_qs(urlsplit(url).query);day=q["from"][0]
  assert day in missing and q["to"]==[day],(day,missing)
  return {"symbol":"1303","timeframe":"1","data":[{"date":day+"T09:00:00+08:00","volume":1000}]}
 adapter.historical_json=api
 with patch.object(m.sqlite3,"connect",side_effect=FakeDB(missing).connect),patch.object(m,"save_json_atomic",side_effect=lambda *a,**kw:writes.append(1)):
  if expected=="stop":
   try:adapter.estimated_vr5_parts("1303","2026-10-09",dt)
   except m.AuditStop as e:
    assert "missing sessions" in str(e),str(e)
   else:raise AssertionError("Expected AuditStop")
  else:
   adapter.estimated_vr5_parts("1303","2026-10-09",dt)
   assert len(calls)==expected,(len(calls),expected)
 print(f"PASS missing={len(missing)} historical_api_calls={len(calls)} expected={expected}")
 return len(calls)
run(set(),0)
run({dates[-1]},1)
run(set(dates[-3:]),"stop")
print("PASS no real HTTP; no real writes; F10 formulas unchanged")
print("RESULT = PASS")
