#!/usr/bin/env python3
"""Isolated A >2 missing F10 -> NO_VCP -> B handoff test; no real side effects."""
import os,sys,importlib.util
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
os.environ.update(A_F11_OFFLINE_STAGING="1",A_LAST_COMPLETED_SESSION="2026-10-08",A_SHARED_DAILY_DB="/var/data/stock-alert/shared_history_stage_v1.sqlite3",PRODUCTION_STATE_DIR="/var/data/stock-alert")
p=Path("/tmp/a_f10_no_vcp_staging.py")
if not p.exists():raise SystemExit("STOP staged file missing")
spec=importlib.util.spec_from_file_location("a_f10_no_vcp",p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
dt=datetime(2026,10,9,10,30,tzinfo=ZoneInfo("Asia/Taipei"))
def run(change,close,expected):
 hits=[];calls=[]
 with patch.object(m,"now_tw",return_value=dt),patch.object(m,"save_json_atomic",lambda *a,**k:None),patch.object(m,"append_event",lambda *a,**k:None),patch.object(m,"append_queue_shadow",lambda *a,**k:None),patch.object(m,"record_a_scan_mother_identity",lambda *a,**k:None):
  a=m.FugleAdapter("OFFLINE");a.history_cache={}
  a.snapshot=lambda:[{"stock_id":"1303","name":"TEST","date":"2026-10-09","close":close,"change_rate":change,"total_volume":6000,"total_amount":60000000}]
  def missing(*args):
   calls.append(1)
   raise m.AuditStop("1303 F10 DB incomplete: 3 missing sessions (cap=2); defer instead of bulk historical API")
  a.estimated_vr5_parts=missing
  sc=object.__new__(m.Scanner);sc.adapter=a;sc.selector=m.StrongSelector(track_path=None);sc.bridge_url=None
  sc.state={"discovered":{},"volume_armed":{},"queue_waiting":{}}
  sc.apply_wait_data_results=lambda:0
  sc.handoff_hit=lambda hit,day:hits.append(hit) or True
  out=sc.scan_once()
  assert len(out)==expected,(change,close,out)
  assert len(hits)==expected
  if expected:
   assert out[0]["source"]=="NO_VCP" and out[0]["estimatedVr5"] is None and out[0]["evgPct"] is None
  assert len(calls)==1
  print(f"PASS change={change} close={close} NO_VCP_handoffs={len(hits)}")
run(4.0,10000,1)
run(2.0,10000,0)
run(4.0,0.01,0)
print("PASS | >2 F10 misses route to NO_VCP only if original price gates pass")
print("PASS | no real HTTP, Bridge, LINE, or writes")
print("RESULT = PASS")
