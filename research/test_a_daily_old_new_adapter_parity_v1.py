#!/usr/bin/env python3
"""Offline shared SQLite vs legacy-cache adapter parity using SAME source rows.
This is a conversion/branch parity test, NOT independent Fugle-source parity.
"""
import importlib.util, os, sqlite3, sys, time
p="/tmp/fugle_a_scanner_db_test.py"
spec=importlib.util.spec_from_file_location("a_parity_offline",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
m.http_json=lambda *a,**k: (_ for _ in ()).throw(AssertionError("HTTP forbidden"))
m.save_json_atomic=lambda *a,**k: (_ for _ in ()).throw(AssertionError("write forbidden"))
os.environ["A_LAST_COMPLETED_SESSION"]="2026-10-08"
db="/var/data/stock-alert/shared_history_stage_v1.sqlite3"
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
symbols=[r[0] for r in con.execute("SELECT symbol FROM fetch_status ORDER BY symbol")]
snapshot="2026-10-12"; start=time.monotonic(); failures=[]
for sym in symbols:
    rows=con.execute("SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? ORDER BY day",(sym,)).fetchall()
    new=m.FugleAdapter("OFFLINE");new.history_cache={};new.daily_cache={}
    actual=new.daily_history_local_ready(sym,snapshot)
    old=m.FugleAdapter("OFFLINE");old.history_cache={
        "daily_static|"+sym:[{"date":ds,"close":close,"volume_zhang":vol} for ds,close,vol in rows],
        "daily_static_covered|"+sym:"2026-10-11"
    };old.daily_cache={}
    old._shared_daily_history=lambda *a,**k: None
    expected=old.daily_history_local_ready(sym,snapshot)
    if actual != expected:
        failures.append((sym,len(actual or []),len(expected or [])))
con.close()
print("TOTAL =",len(symbols))
print("PARITY_PASS =",len(symbols)-len(failures))
print("PARITY_FAIL =",len(failures))
print("FAIL_EXAMPLES =",failures[:10])
print("ELAPSED_SEC =",round(time.monotonic()-start,2))
print("NOTE = same-source adapter parity only; independent old Fugle values not verified")
print("HTTP_AND_WRITES = BLOCKED")
assert not failures
