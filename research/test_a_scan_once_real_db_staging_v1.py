#!/usr/bin/env python3
"""Isolated scan_once integration: real SQLite + real selector, synthetic snapshot; NO I/O writes."""
import os,sys,importlib.util
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
os.environ.update(A_F11_OFFLINE_STAGING="1",A_LAST_COMPLETED_SESSION="2026-10-08",A_SHARED_DAILY_DB="/var/data/stock-alert/shared_history_stage_v1.sqlite3",PRODUCTION_STATE_DIR="/var/data/stock-alert")
p=Path("/tmp/a_f11_offline_staging_test.py")
if not p.is_file():raise SystemExit("STOP staging scanner file missing")
spec=importlib.util.spec_from_file_location("a_scan_db_integrated",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
fake_dt=datetime(2026,10,9,10,30,tzinfo=ZoneInfo("Asia/Taipei"))
counts={"snapshot":0,"f10":0,"selector":0,"write_attempts":0,"network":0}
def no_http(*a,**kw):counts["network"]+=1;raise AssertionError("NETWORK FORBIDDEN")
def no_write(*a,**kw):counts["write_attempts"]+=1
class NoWorker:
 def drain_results(self):return []
 def submit(self,*args):raise AssertionError("UNEXPECTED WAIT_DATA")
snap={"stock_id":"1303","name":"TEST","date":"2026-10-09","close":100.0,"change_rate":4.0,"total_volume":6000.0,"total_amount":60000000.0}
with patch.object(m,"http_json",side_effect=no_http),patch.object(m.FugleAdapter,"historical_json",side_effect=no_http),patch.object(m,"now_tw",return_value=fake_dt),patch.object(m,"save_json_atomic",side_effect=no_write),patch.object(m,"append_event",side_effect=no_write),patch.object(m,"append_queue_shadow",side_effect=no_write),patch.object(m,"record_a_scan_mother_identity",side_effect=no_write):
 a=m.FugleAdapter("OFFLINE");a.history_cache={}
 scanner=object.__new__(m.Scanner)
 scanner.adapter=a;scanner.selector=m.StrongSelector(track_path=None);scanner.bridge_url=None
 scanner.state={"discovered":{},"volume_armed":{},"queue_waiting":{}}
 scanner.wait_data_worker=NoWorker()
 def snapshot():counts["snapshot"]+=1;return [dict(snap)]
 a.snapshot=snapshot
 original=a.estimated_vr5_parts
 def f10(*args):counts["f10"]+=1;return original(*args)
 a.estimated_vr5_parts=f10
 old_selector=scanner.selector.select_one
 def selector(*args,**kwargs):counts["selector"]+=1;return old_selector(*args,**kwargs)
 scanner.selector.select_one=selector
 # Never emit bridge traffic even if selector matches.
 scanner.handoff_hit=lambda hit,day: False
 for i in range(2):
  result=scanner.scan_once()
  assert isinstance(result,list)
  print("PASS scan",i+1,"selected",len(result),"F10_calls",counts["f10"])
 assert counts["snapshot"]==2 and counts["selector"]>=1,counts
 assert counts["f10"]>=1,counts
 assert counts["network"]==0,counts
 assert "1303" in a.daily_cache and "estvr5|1303|2026-10-09" in a._estvr5_cache
 print("PASS | real A scan_once + real daily/F10/F11/F12 + real selector")
 print("PASS | HTTP=0, disk writes intercepted, Bridge=0, LINE=0")
 print("RESULT = PASS")
