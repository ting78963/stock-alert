#!/usr/bin/env python3
"""Offline A select_one parity: same-source old-cache vs shared-SQLite, no network/writes.
Synthetic intraday quotes are NOT historical recognition replay.
"""
import importlib.util,os,sys,sqlite3,time
p="/tmp/fugle_a_scanner_db_test.py"
spec=importlib.util.spec_from_file_location("a_select_parity",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
def forbidden(*args,**kwargs): raise AssertionError("network/write forbidden")
m.http_json=forbidden;m.save_json_atomic=forbidden
os.environ["A_LAST_COMPLETED_SESSION"]="2026-10-08"
db="/var/data/stock-alert/shared_history_stage_v1.sqlite3"
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
symbols=[r[0] for r in con.execute("SELECT symbol FROM fetch_status ORDER BY symbol")]
new=m.FugleAdapter("OFFLINE");new.history_cache={};new.daily_cache={}
old=m.FugleAdapter("OFFLINE");old.history_cache={};old.daily_cache={}
old._shared_daily_history=lambda *a,**k:None
snapshot="2026-10-12";cases=[("flat",0.5,1.0),("up3",3.5,1.5),("up7",7.0,3.0)]
checked=0;fails=[];start=time.monotonic()
for sym in symbols:
    rows=con.execute("SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? ORDER BY day",(sym,)).fetchall()
    old.history_cache={"daily_static|"+sym:[{"date":ds,"close":close,"volume_zhang":vol} for ds,close,vol in rows],"daily_static_covered|"+sym:"2026-10-11"}
    old.daily_cache={};new.daily_cache={}
    bnew=new.daily_history_local_ready(sym,snapshot);bold=old.daily_history_local_ready(sym,snapshot)
    if bnew!=bold:
        fails.append((sym,"daily mismatch"));continue
    if not bnew: fails.append((sym,"no bars"));continue
    last=bnew[-1].close
    for label,chg,mult in cases:
        quote={"stock_id":sym,"date":snapshot,"name":sym,"close":last*(1+chg/100),"change_rate":chg,"total_volume":max(1,bnew[-1].volume_zhang)*mult,"_volume_display_ratio":mult}
        meta={"market":"TSE","securityType":"01","industry":""}
        a=m.StrongSelector(track_path=None).select_one(quote,meta,bnew)
        b=m.StrongSelector(track_path=None).select_one(quote,meta,bold)
        checked+=1
        if a!=b: fails.append((sym,label,a,b))
con.close()
print("STOCKS =",len(symbols))
print("SELECTOR_CASES =",checked)
print("PARITY_FAIL =",len(fails))
print("FAIL_EXAMPLES =",fails[:5])
print("ELAPSED_SEC =",round(time.monotonic()-start,2))
print("LIMITATION = synthetic quotes; no real-time replay or B handoff timing tested")
print("HTTP_AND_WRITES = BLOCKED")
assert not fails
