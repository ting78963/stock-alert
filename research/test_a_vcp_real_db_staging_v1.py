#!/usr/bin/env python3
"""Real DB -> original VCP and NO_VCP selector, read only; no network."""
import os,sys,importlib.util
from pathlib import Path
from unittest.mock import patch
os.environ.update(A_F11_OFFLINE_STAGING="1",A_LAST_COMPLETED_SESSION="2026-10-08",A_SHARED_DAILY_DB="/var/data/stock-alert/shared_history_stage_v1.sqlite3",PRODUCTION_STATE_DIR="/var/data/stock-alert")
p=Path("/tmp/a_f11_offline_staging_test.py")
if not p.is_file(): raise SystemExit("STOP staging scanner file missing")
spec=importlib.util.spec_from_file_location("a_vcp_real_db",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
def no_http(*args,**kwargs):raise AssertionError("unexpected HTTP")
with patch.object(m,"http_json",side_effect=no_http),patch.object(m.FugleAdapter,"historical_json",side_effect=no_http):
    a=m.FugleAdapter("OFFLINE")
    a.history_cache={}
    sel=m.StrongSelector()
    for sym in ("1303","2323","6236","2073"):
        bars=a.daily_history_local_ready(sym,"2026-10-09")
        assert bars is not None and len(bars)>=60,(sym,"insufficient VCP daily")
        closes=[x.close for x in bars]; vols=[x.volume_zhang for x in bars]; dates=[x.date for x in bars]
        v=sel.analyze_vcp(closes,vols,sym,dates)
        assert isinstance(v,dict) and v.get("status")!="data_insufficient",(sym,v)
        assert len(dates)==len(set(dates)) and dates==sorted(dates),(sym,"date order")
        assert dates[-1]<"2026-10-09",(sym,"future data")
        print("PASS",sym,"VCP",v.get("status"),"sessions",len(bars),"latest",dates[-1])
print("PASS | VCP real DB 4 symbols, suspended-date gaps tolerated, zero API")
print("RESULT = PASS")
