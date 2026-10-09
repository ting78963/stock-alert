#!/usr/bin/env python3
"""Read-only VCP actual database regression; insufficient history is a valid outcome."""
import os,sys,importlib.util
from pathlib import Path
from unittest.mock import patch
os.environ.update(A_F11_OFFLINE_STAGING="1",A_LAST_COMPLETED_SESSION="2026-10-08",A_SHARED_DAILY_DB="/var/data/stock-alert/shared_history_stage_v1.sqlite3",PRODUCTION_STATE_DIR="/var/data/stock-alert")
p=Path("/tmp/a_f11_offline_staging_test.py")
if not p.is_file():raise SystemExit("STOP: staging scanner module missing")
spec=importlib.util.spec_from_file_location("a_vcp_regression_v2",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
def blocked(*args,**kwargs):raise AssertionError("UNEXPECTED HTTP")
with patch.object(m,"http_json",side_effect=blocked),patch.object(m.FugleAdapter,"historical_json",side_effect=blocked):
    a=m.FugleAdapter("OFFLINE");a.history_cache={}
    sel=m.StrongSelector()
    for sym in ("1303","2323","6236","2073"):
        bars=a.daily_history_local_ready(sym,"2026-10-09")
        assert bars is not None,(sym,"unexpected database miss")
        dates=[b.date for b in bars]; closes=[b.close for b in bars]; vols=[b.volume_zhang for b in bars]
        assert dates==sorted(set(dates)) and all(d<"2026-10-09" for d in dates),sym
        v=sel.analyze_vcp(closes,vols,sym,dates)
        assert isinstance(v,dict),sym
        if len(bars)<30:
            assert v["status"]=="data_insufficient",(sym,len(bars),v)
            print(f"PASS {sym}: {len(bars)} rows -> data_insufficient (no invented bars)")
        else:
            assert v["status"]!="data_insufficient",(sym,len(bars),v)
            print(f"PASS {sym}: {len(bars)} rows -> {v['status']}")
print("PASS | Real DB VCP semantics, no HTTP, no writes")
print("RESULT = PASS")
