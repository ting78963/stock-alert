#!/usr/bin/env python3
"""Offline 2026-10-22 SURGE replay with candidate's real F10 gate. Read-only."""
import json,sqlite3,urllib.request,types,sys
from pathlib import Path
from datetime import datetime
from collections import Counter
ROOT=Path("/var/data/stock-alert")
SHA="1587dccc3fef49ea47458173e832d145c50490d9"
URL=f"https://raw.githubusercontent.com/ting78963/stock-alert/{SHA}/fugle_a_scanner_v2_4.py"
mod=types.ModuleType("offline_candidate_a");mod.__file__=URL;sys.modules[mod.__name__]=mod
exec(compile(urllib.request.urlopen(URL,timeout=20).read().decode(),"candidate_a.py","exec"),mod.__dict__)
def no_network(*args,**kwargs): raise RuntimeError("OFFLINE_NETWORK_OR_FALLBACK_FORBIDDEN")
adapter=mod.FugleAdapter.__new__(mod.FugleAdapter)
adapter.history_cache={}
adapter._estvr5_cache={}
adapter.historical_json=no_network
adapter.daily_history=no_network
scanner=mod.Scanner.__new__(mod.Scanner)
scanner.adapter=adapter
day="2026-10-22"
db=ROOT/"f10_baseline_v1.sqlite3"
if not db.is_file(): raise SystemExit("STOP: F10 DB absent")
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
files=sorted((ROOT/"f15_eod/trajectory_v1"/day).glob("*.json"))
counts=Counter()
print("symbol,first_1000,first_surge_pass,first_pass_est_vr5,first_pass_evg1,status,reason")
for p in files:
    if p.name=="manifest.json":continue
    d=json.loads(p.read_text(encoding="utf-8"))
    symbol=str(d["identity"]["stock_id"])
    bars=d.get("trajectory_raw_1m",[])
    if not bars:counts["NO_BARS"]+=1;continue
    n=con.execute("SELECT COUNT(*) FROM f10_day WHERE symbol=? AND day<?",(symbol,day)).fetchone()[0]
    if n<10:counts["F10_INCOMPLETE"]+=1;print(f"{symbol},,,,,UNKNOWN,F10_INCOMPLETE");continue
    first1000=firstpass=None
    pass_metrics=None
    status=reason="BELOW_1000"
    last=-1
    for bar in sorted(bars,key=lambda x:x["minute"]):
        tm=str(bar["minute"])[:5]
        cum=float(bar["cum_volume"])
        if cum<last:raise SystemExit(f"STOP: nonmonotonic volume {symbol}")
        last=cum
        if cum<1000:continue
        if first1000 is None:first1000=tm
        ts=datetime.fromisoformat(day+"T"+tm+":00+08:00")
        snap={"stock_id":symbol,"date":day,"total_volume":cum}
        try:
            status,reason,metrics=scanner.snapshot_surge_decision(snap,day,ts)
        except Exception as e:
            status,reason="ERROR",type(e).__name__+":"+str(e)[:100]
            break
        if status=="PASS":
            firstpass=tm;pass_metrics=metrics;break
        if status=="UNKNOWN":break
    counts[status]+=1
    vr=pass_metrics.get("estimated_vr5") if pass_metrics else ""
    evg=pass_metrics.get("evg1") if pass_metrics else ""
    print(f"{symbol},{first1000 or ''},{firstpass or ''},{vr},{evg},{status},{reason}")
con.close()
print("SUMMARY",json.dumps({"date":day,"checked":sum(counts.values()),"counts":dict(counts),
 "caveats":"F15-selected stocks only; 1-minute OHLCV, not full-market snapshots; first-pass minute is bar-level; no LINE; no state writes"},ensure_ascii=False))
