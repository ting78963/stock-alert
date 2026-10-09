#!/usr/bin/env python3
"""Read-only integration audit: verified session + DB watermark + A adapter.
No production env changes, no HTTP, no writes. Does NOT install automatic wiring.
"""
import importlib.util,sqlite3,sys,os
from datetime import date,timedelta
from pathlib import Path
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
a=load("a_session_audit","/tmp/fugle_a_scanner_db_test.py")
gate=load("gate_session_audit","twse_session_gate_v1.py")
def forbidden(*args,**kwargs):raise AssertionError("STOP: HTTP/write attempted")
gate.fetch_schedule=forbidden;a.http_json=forbidden;a.save_json_atomic=forbidden
# This is a calendar FIXTURE. The live official API was checked separately.
rows=[{"Date":"1151009","Name":"國慶日補假，停止交易"},{"Date":"1151010","Name":"國慶日，停止交易"}]
snapshot=date(2026,10,12)
required=snapshot-timedelta(days=1)
while not gate.is_scheduled_open(required,rows=rows):required-=timedelta(days=1)
assert required.isoformat()=="2026-10-08"
db=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
assert db.is_file(),"STOP: shared SQLite missing"
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
status=con.execute("SELECT symbol,covered_through FROM fetch_status ORDER BY symbol").fetchall()
bad=[(s,d) for s,d in status if not d or str(d)[:10]<required.isoformat()]
assert len(status)==1447 and not bad,(len(status),bad[:5])
con.close()
os.environ["A_LAST_COMPLETED_SESSION"]=required.isoformat()
adapter=a.FugleAdapter("OFFLINE");adapter.history_cache={};adapter.daily_cache={}
ok=0;missing=[]
for symbol,_ in status:
    bars=adapter.daily_history_local_ready(symbol,snapshot.isoformat())
    if bars and all(b.date<snapshot.isoformat() for b in bars):ok+=1
    else:missing.append(symbol)
assert not missing,(len(missing),missing[:10])
# Negative gate: simulate requiring a session not yet covered by the DB.
os.environ["A_LAST_COMPLETED_SESSION"]="2026-10-13"
probe=a.FugleAdapter("OFFLINE");probe.history_cache={};probe.daily_cache={}
assert probe._shared_daily_history(status[0][0],"2026-10-14") is None
print("SNAPSHOT =",snapshot)
print("REQUIRED_SESSION =",required)
print("DB_COVERAGE_PASS =",len(status))
print("A_LOCAL_READY_PASS =",ok)
print("UNCOVERED_SESSION_FALLBACK = VERIFIED")
print("CALENDAR = FIXTURE (not live API)")
print("AUTO_WIRING = NOT INSTALLED")
print("HTTP_AND_WRITES = BLOCKED")
