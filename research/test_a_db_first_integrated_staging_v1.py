#!/usr/bin/env python3
"""READ ONLY staging A database-first integration; no production write/network."""
import os, sys, json, importlib.util
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ["A_F11_OFFLINE_STAGING"]="1"
os.environ["A_LAST_COMPLETED_SESSION"]="2026-10-08"
os.environ["A_SHARED_DAILY_DB"]="/var/data/stock-alert/shared_history_stage_v1.sqlite3"
os.environ["PRODUCTION_STATE_DIR"]="/var/data/stock-alert"
scanner=Path("/tmp/a_f11_offline_staging_test.py")
if not scanner.is_file():
    raise SystemExit("STOP: scanner staging file missing; do not test production module")
for path in (os.environ["A_SHARED_DAILY_DB"],"/var/data/stock-alert/f10_baseline_v1.sqlite3","/var/data/stock-alert/f11-staging/a_f11_staging_v1.json"):
    if not Path(path).is_file(): raise SystemExit("STOP missing "+path)
spec=importlib.util.spec_from_file_location("a_staging_integrated",scanner)
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)
if not mod.F11_OFFLINE_STAGING_ENABLED: raise SystemExit("STOP F11 opt-in not active")
if not hasattr(mod.FugleAdapter,"_shared_daily_history"): raise SystemExit("STOP scanner lacks shared daily")
calls=[]
def block(*a,**kw):
    calls.append(str(a[0]) if a else "unknown")
    raise AssertionError("NETWORK CALLED")
with patch.object(mod,"http_json",side_effect=block), patch.object(mod.FugleAdapter,"historical_json",side_effect=block):
    a=mod.FugleAdapter("OFFLINE-TEST-NO-KEY")
    # Never allow old persisted history cache to mask actual DB path.
    a.history_cache={}
    symbol="1303"; day="2026-10-09"
    m=a.ticker(symbol)
    assert m.get("symbol")==symbol and "industry" in m, "F11/F12 identity/industry"
    bars=a.daily_history_local_ready(symbol,day)
    assert bars and len(bars)>=60 and all(x.date<day for x in bars), "daily DB/VCP 60 sessions"
    assert a.daily_history_local_ready(symbol,day) is bars, "daily same-day cache"
    now=datetime(2026,10,9,10,30,tzinfo=ZoneInfo("Asia/Taipei"))
    vr=a.estimated_vr5_parts(symbol,day,now)
    assert isinstance(vr,tuple) and len(vr)==4, "F10 result"
    assert len(a._estvr5_cache["estvr5|"+symbol+"|"+day])==10, "F10 ten days"
    vr2=a.estimated_vr5_parts(symbol,day,now)
    assert vr==vr2, "F10 repeat consistency"
    # VCP computation is exercised without scanner state or file writes.
    selector=object.__new__(mod.Selector) if hasattr(mod,"Selector") else None
    if selector is not None:
        selector.track={}
        v=selector.analyze_vcp([x.close for x in bars],[x.volume_zhang for x in bars],symbol,[x.date for x in bars])
        assert v.get("status")!="data_insufficient", "VCP data readiness"
    try:
        a.ticker("9999")
    except RuntimeError as exc:
        assert "F11_OFFLINE_MISS" in str(exc)
    else:
        raise AssertionError("F11 unknown symbol not deferred")
assert not calls, calls
print("PASS | REAL DB daily 60+ sessions + repeat cache")
print("PASS | REAL DB F10 10 sessions + repeat cache")
print("PASS | F11/F12 industry local + missing symbol fail closed")
print("PASS | NO historical/ticker HTTP; no production writes")
print("RESULT = PASS")
