#!/usr/bin/env python3
"""F10 incomplete NO_VCP -> real handoff_hit dedupe regression. Mock bridge and writes."""
import os,sys,importlib.util
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
os.environ.update(A_F11_OFFLINE_STAGING="1",A_LAST_COMPLETED_SESSION="2026-10-08",A_SHARED_DAILY_DB="/var/data/stock-alert/shared_history_stage_v1.sqlite3",PRODUCTION_STATE_DIR="/var/data/stock-alert")
p=Path("/tmp/a_f10_no_vcp_staging.py")
if not p.is_file():raise SystemExit("STOP staging scanner missing")
spec=importlib.util.spec_from_file_location("a_f10_dedupe",p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
dt=datetime(2026,10,9,10,30,tzinfo=ZoneInfo("Asia/Taipei"))
def case(fail_first):
 calls=[];events=[]
 with patch.object(m,"now_tw",return_value=dt),patch.object(m,"save_json_atomic",lambda *a,**k:None),patch.object(m,"append_event",lambda e:events.append(e)),patch.object(m,"append_queue_shadow",lambda *a,**k:None),patch.object(m,"record_a_scan_mother_identity",lambda *a,**k:None):
  a=m.FugleAdapter("OFFLINE");a.history_cache={}
  a.snapshot=lambda:[{"stock_id":"1303","name":"TEST","date":"2026-10-09","close":10000,"change_rate":4.0,"total_volume":6000,"total_amount":60000000}]
  def missing(*args):raise m.AuditStop("1303 F10 DB incomplete: 3 missing sessions (cap=2)")
  a.estimated_vr5_parts=missing
  sc=object.__new__(m.Scanner);sc.adapter=a;sc.selector=m.StrongSelector(track_path=None);sc.bridge_url="MOCK_ONLY"
  sc.state={"discovered":{},"volume_armed":{},"queue_waiting":{}}
  sc.apply_wait_data_results=lambda:0
  def bridge(payload):
   calls.append(dict(payload))
   if fail_first and len(calls)==1:raise RuntimeError("simulated B bridge failure")
  sc.bridge_send=bridge
  for i in range(3 if fail_first else 2):
   result=sc.scan_once()
   if i==0 and fail_first:
    assert not sc.already_sent("2026-10-09","1303")
   else:
    assert sc.already_sent("2026-10-09","1303")
  expected=2 if fail_first else 1
  assert len(calls)==expected,(fail_first,calls)
  assert all(x["source"]=="NO_VCP" for x in calls)
  assert len([e for e in events if e.get("type")=="discovery"])==1
  print(f"PASS fail_first={fail_first} bridge_attempts={len(calls)} discovery_events=1")
case(False)
case(True)
print("PASS | real handoff_hit + mark_sent dedupe; no real Bridge/LINE/HTTP/writes")
print("RESULT = PASS")
