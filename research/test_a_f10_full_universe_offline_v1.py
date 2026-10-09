#!/usr/bin/env python3
"""Read-only full-universe A F10 adapter test, forbids network and production writes."""
import importlib.util, os, sys, sqlite3, time
from datetime import datetime
p=os.environ.get("A_TEST_MODULE","/tmp/fugle_a_scanner_db_test.py")
spec=importlib.util.spec_from_file_location("a_f10_offline",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
os.environ["A_LAST_COMPLETED_SESSION"]="2026-10-08"
def forbidden(*args,**kwargs):
    raise AssertionError("NETWORK OR WRITE FORBIDDEN")
m.http_json=forbidden
m.save_json_atomic=forbidden
a=m.FugleAdapter("OFFLINE_TEST");a.history_cache={};a.daily_cache={}
conn=sqlite3.connect("file:/var/data/stock-alert/f10_baseline_v1.sqlite3?mode=ro",uri=True)
symbols=[r[0] for r in conn.execute("SELECT DISTINCT symbol FROM f10_day ORDER BY symbol")];conn.close()
now=datetime(2026,10,12,10,0)
start=time.monotonic();failed=[];passed=0
for symbol in symbols:
    try:
        result=a.estimated_vr5_parts(symbol,"2026-10-12",now)
        assert len(result)==4 and all(isinstance(v,(int,float)) for v in result),result
        passed+=1
    except Exception as e:
        failed.append((symbol,type(e).__name__,str(e)))
print("TOTAL =",len(symbols))
print("PASS =",passed)
print("FAIL =",len(failed))
print("FAIL_EXAMPLES =",failed[:20])
print("ELAPSED_SEC =",round(time.monotonic()-start,2))
print("HTTP_AND_WRITES = BLOCKED")
assert not failed
