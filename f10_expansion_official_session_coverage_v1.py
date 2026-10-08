#!/usr/bin/env python3
"""F10 official-session window coverage audit; read-only, no Fugle requests."""
import csv,json,sqlite3,sys
from collections import Counter
from datetime import date,timedelta
from pathlib import Path
from twse_session_gate_v1 import fetch_schedule,is_scheduled_open
R=Path("/var/data/stock-alert/_f10_expansion_research")
S=R/"f10_expansion_stage_v1.sqlite3"
P=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
def stop(s):raise RuntimeError(s)
def main():
    roster=json.loads((R/"f10_expansion_roster_v1.json").read_text(encoding="utf-8"))
    with (R/"f10_expansion_add_1014_v1.csv").open(encoding="utf-8-sig",newline="") as f:
        names=[r["symbol"] for r in csv.DictReader(f)]
    if len(names)!=1014 or len(set(names))!=1014 or set(names)!=set(roster["new_symbols"]):stop("frozen roster mismatch")
    wanted=set(names)-{"1589"}
    with sqlite3.connect("file:"+str(S)+"?mode=ro",uri=True) as c,sqlite3.connect("file:"+str(P)+"?mode=ro",uri=True) as prod:
        members={s for (s,) in prod.execute("SELECT symbol FROM member")}
        if len(members)!=434 or members&set(names):stop("production membership mismatch")
        statuses=dict(c.execute("SELECT symbol,status FROM audit"))
        if set(statuses)!=set(names) or statuses.get("1589")!="FAIL" or any(statuses.get(s)!="PASS" for s in wanted):stop("audit identity/status mismatch")
        grouped={}
        for s,d in c.execute("SELECT symbol,day FROM f10_day ORDER BY symbol,day"):
            grouped.setdefault(s,[]).append(d)
        if set(grouped)!=wanted:stop("staging symbol mismatch")
        all_days=[d for v in grouped.values() for d in v]
        if not all_days:stop("no stage days")
        end=date.fromisoformat(max(all_days))
        start=end-timedelta(days=40)
        print("[OFFICIAL] fetching TWSE holiday schedule (one request)",flush=True)
        rows=fetch_schedule(timeout=15)
        sessions=[]
        day=start
        while day<=end:
            if is_scheduled_open(day,rows=rows):sessions.append(day.isoformat())
            day+=timedelta(days=1)
        if len(sessions)<11:stop("official schedule yielded fewer than 11 sessions")
        # Fail closed for known 2026 TWSE holiday API omission/misclassification.\n        # These are independently identified full-market closure dates; do not modify shared production gate here.\n        known_closed={"2026-09-25","2026-09-28"}\n        wrongly_open=sorted(known_closed.intersection(sessions))\n        if wrongly_open:\n            print("[SCHEDULE CONFLICT] official gate incorrectly marked closed dates as open:",wrongly_open,flush=True)\n            print("[STOP] session gate needs independent holiday verification; no coverage conclusion",flush=True)\n            return\n        window=sessions[-11:]
        counts=Counter()
        missing_by_day=Counter()
        gaps=[]
        for s in sorted(wanted):
            observed=set(grouped[s])
            missing=[d for d in window if d not in observed]
            counts[len(missing)]+=1
            missing_by_day.update(missing)
            if missing:gaps.append((s,len(observed),missing,max(observed)))
        print("[PASS] official session schedule verified",flush=True)
        print("[OFFICIAL LAST 11]",",".join(window),flush=True)
        print("[COVERAGE MISSING-COUNT DISTRIBUTION]",sorted(counts.items()),flush=True)
        print("[FULL WINDOW COVERAGE]",counts[0],"/",len(wanted),flush=True)
        print("[MISSING PER DATE]",sorted(missing_by_day.items()),flush=True)
        print("[GAP SYMBOL COUNT]",len(gaps),flush=True)
        print("[GAP DETAILS] first 40 symbols; absence is NOT confirmed zero-volume")
        for s,n,missing,last in gaps[:40]:
            print(s,"stored_days=",n,"last=",last,"missing=",",".join(missing),flush=True)
        if len(gaps)>40:print("[GAP DETAILS TRUNCATED] remaining=",len(gaps)-40,flush=True)
        print("[NO ZERO FILL] [READ ONLY] [NO PRODUCTION WRITE] [NO A/B CHANGE]",flush=True)
if __name__=="__main__":
    try:main()
    except Exception as e:print("[STOP]",type(e).__name__,str(e),file=sys.stderr,flush=True);sys.exit(2)
