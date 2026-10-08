#!/usr/bin/env python3
"""Read-only, fail-closed pre-integration audit of F10 staging."""
import csv,json,sqlite3,sys
from collections import Counter
from pathlib import Path
R=Path("/var/data/stock-alert/_f10_expansion_research")
S=R/"f10_expansion_stage_v1.sqlite3"
P=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
def stop(msg): raise RuntimeError(msg)
def main():
    roster=json.loads((R/"f10_expansion_roster_v1.json").read_text(encoding="utf-8"))
    with (R/"f10_expansion_add_1014_v1.csv").open(encoding="utf-8-sig",newline="") as f:
        names=[r["symbol"] for r in csv.DictReader(f)]
    if len(names)!=1014 or len(set(names))!=1014 or set(names)!=set(roster["new_symbols"]): stop("frozen roster identity mismatch")
    expected=set(names)-{"1589"}
    with sqlite3.connect("file:"+str(P)+"?mode=ro",uri=True) as prod,sqlite3.connect("file:"+str(S)+"?mode=ro",uri=True) as c:
        members={r[0] for r in prod.execute("SELECT symbol FROM member")}
        if len(members)!=434: stop(f"production member count changed: {len(members)}")
        if members & set(names): stop("staging and production membership overlap")
        statuses=dict(c.execute("SELECT symbol,status FROM audit"))
        if set(statuses)!=set(names): stop("audit identities do not match frozen roster")
        if statuses.get("1589")!="FAIL" or any(statuses[s]!="PASS" for s in expected): stop("unexpected audit status")
        stage_symbols={r[0] for r in c.execute("SELECT DISTINCT symbol FROM f10_day")}
        if stage_symbols!=expected: stop("staged data symbol identities do not match 1013 PASS candidates")
        sparse=[]; hist=Counter(); days_by_symbol={}; invalid=0
        for symbol,day,full,raw in c.execute("SELECT symbol,day,full,pts_json FROM f10_day ORDER BY symbol,day"):
            pts=json.loads(raw)
            if not 0<float(full) or not isinstance(pts,list) or not pts: stop(f"{symbol} {day} empty/invalid")
            seen=set(); last=-1.; prior=""
            for point in pts:
                if not isinstance(point,list) or len(point)!=2: stop(f"{symbol} {day} invalid point")
                tm,v=point
                if not isinstance(tm,str) or tm in seen or tm<prior or float(v)<last or float(v)<0: stop(f"{symbol} {day} bad minute ordering/volume")
                seen.add(tm);prior=tm;last=float(v)
            if abs(last-float(full))>0.0001: stop(f"{symbol} {day} final cumulative volume mismatch")
            days_by_symbol.setdefault(symbol,[]).append(day)
        for symbol in sorted(expected):
            days=days_by_symbol.get(symbol,[])
            if len(days)<5 or len(days)>11 or days!=sorted(set(days)): stop(f"{symbol} invalid day count/duplicates")
            hist[len(days)]+=1
            if len(days)<11: sparse.append((symbol,len(days),days))
        print("[PASS] frozen roster=1014 excluded=1589 stage PASS=1013 production members=434 nonoverlap",flush=True)
        print("[PASS] per-minute cumulative integrity and day identities",flush=True)
        print("[DISTRIBUTION]",sorted(hist.items()),flush=True)
        print("[DAY ROWS]",sum(len(x) for x in days_by_symbol.values()),flush=True)
        canonical=Counter(day for days in days_by_symbol.values() for day in days)
        print("[COMMON DATES]",canonical.most_common(15),flush=True)
        print("[SPARSE DETAILS] (observed dates; absent dates not presumed zero)")
        for symbol,n,days in sparse:
            missing=[d for d,_ in canonical.most_common(11) if d not in days]
            print(symbol,"sessions=",n,"observed=",",".join(days),"missing_vs_common=",",".join(missing),flush=True)
        print("[READ ONLY] [NO PRODUCTION WRITE] [NO A/B CHANGE]",flush=True)
if __name__=="__main__":
    try:main()
    except Exception as e:print("[STOP]",type(e).__name__,str(e),file=sys.stderr,flush=True);sys.exit(2)
