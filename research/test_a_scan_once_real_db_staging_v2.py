#!/usr/bin/env python3
"""A scan regression: no-anomaly and armed path, real DB, isolated side effects."""
import os,sys,importlib.util
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
os.environ.update(A_F11_OFFLINE_STAGING="1",A_LAST_COMPLETED_SESSION="2026-10-08",A_SHARED_DAILY_DB="/var/data/stock-alert/shared_history_stage_v1.sqlite3",PRODUCTION_STATE_DIR="/var/data/stock-alert")
p=Path("/tmp/a_f11_offline_staging_test.py")
if not p.is_file():raise SystemExit("STOP staging scanner missing")
spec=importlib.util.spec_from_file_location("a_scan_db_v2",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
fake_dt=datetime(2026,10,9,10,30,tzinfo=ZoneInfo("Asia/Taipei"))
counts={"network":0,"selector":0,"f10":0,"bridge":0,"writes_intercepted":0}
def no_http(*a,**kw):counts["network"]+=1;raise AssertionError("HTTP FORBIDDEN")
def no_write(*a,**kw):counts["writes_intercepted"]+=1
class NoWorker:
 def drain_results(self):return []
 def submit(self,*args):raise AssertionError("unexpected WAIT_DATA")
snap={"stock_id":"1303","name":"TEST","date":"2026-10-09","close":100.0,"change_rate":4.0,"total_volume":6000.0,"total_amount":60000000.0}
with patch.object(m,"http_json",side_effect=no_http),patch.object(m.FugleAdapter,"historical_json",side_effect=no_http),patch.object(m,"now_tw",return_value=fake_dt),patch.object(m,"save_json_atomic",side_effect=no_write),patch.object(m,"append_event",side_effect=no_write),patch.object(m,"append_queue_shadow",side_effect=no_write),patch.object(m,"record_a_scan_mother_identity",side_effect=no_write):
 a=m.FugleAdapter("OFFLINE");a.history_cache={}
 sc=object.__new__(m.Scanner);sc.adapter=a;sc.selector=m.StrongSelector(track_path=None);sc.bridge_url=None
 sc.state={"discovered":{},"volume_armed":{},"queue_waiting":{}};sc.wait_data_worker=NoWorker()
 a.snapshot=lambda:[dict(snap)]
 orig_f10=a.estimated_vr5_parts
 def f10(*args):counts["f10"]+=1;return orig_f10(*args)
 a.estimated_vr5_parts=f10
 orig_select=sc.selector.select_one
 def select(*args,**kwargs):counts["selector"]+=1;return orig_select(*args,**kwargs)
 sc.selector.select_one=select
 def no_bridge(hit,day):counts["bridge"]+=1;return False
 sc.handoff_hit=no_bridge
 # 1: normal volume: no forced selector
 assert sc.scan_once()==[]
 assert counts["selector"]==0,"unexpected selector before arming"
 assert "estvr5|1303|2026-10-09" in a._estvr5_cache,"F10 DB cache missing"
 print("PASS normal volume: no structural selector, F10 DB cached")
 # 2: simulate previously valid armed state; do not change formulas or thresholds
 sc.state["volume_armed"].setdefault("2026-10-09",{})["1303"]={"armed_at":"10:29:00","reasons":["EST_VR5_1P5"],"raw_vr5":1.0,"estimated_vr5":1.5,"evg_pct":50.0}
 assert isinstance(sc.scan_once(),list)
 assert counts["selector"]==1,"armed candidate did not reach real selector"
 assert counts["f10"]==1,"armed scan unnecessarily recomputed F10"
 assert counts["network"]==0 and counts["bridge"]==0 or counts["network"]==0,counts
 print("PASS armed candidate: real selector executed, no redundant F10 call")
 print("PASS no HTTP; writes intercepted; Bridge handoff mocked")
 print("RESULT = PASS")
