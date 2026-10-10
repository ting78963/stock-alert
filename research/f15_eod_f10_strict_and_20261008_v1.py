#!/usr/bin/env python3
"""2026-10-08 F15 A queue vs F10 strict-AND historical minute audit.
READ ONLY; NO NETWORK; NO PRODUCTION IMPORTS OR WRITES.
Market-minute eligibility, not actual live observation/handoff.
"""
import bisect, collections, datetime as dt, json, math, sqlite3
from pathlib import Path

ROOT=Path("/var/data/stock-alert")
DAY="2026-10-08"
Q=ROOT/"a_queue_shadow_audit"/DAY/"queue_shadow_audit.jsonl"
F=ROOT/"f15_eod"/(DAY+".json")
DB=ROOT/"f10_baseline_v1.sqlite3"

def curve(raw, full):
    pts=json.loads(raw)
    if not isinstance(pts,list) or not pts or not math.isfinite(float(full)) or float(full)<=0:
        raise ValueError("invalid curve/full")
    times=[]; vols=[]; prev=-1.0
    for pair in pts:
        t,v=pair
        t=str(t);v=float(v)
        if len(t)==5:t+=":00"
        if (times and t<=times[-1]) or not math.isfinite(v) or v<prev or v<0:
            raise ValueError("unordered/nonmonotone curve")
        times.append(t);vols.append(v);prev=v
    if abs(vols[-1]-float(full))>max(1e-6,float(full)*1e-7):
        raise ValueError("curve/full mismatch")
    return times,vols

def at(c,t):
    ts,vs=c
    i=bisect.bisect_right(ts,t)-1
    return vs[i] if i>=0 else 0.0

def main():
    if not all(p.is_file() for p in (Q,F,DB)):
        raise SystemExit("STOP: required input absent")
    candidates=set()
    with Q.open(encoding="utf-8") as fh:
        for line in fh:
            d=json.loads(line)
            if d.get("type")=="QUEUE_ENTER":
                candidates.add(str(d["symbol"]))
    signals=json.loads(F.read_text(encoding="utf-8"))["rows"]
    bplus={str(r["stock_id"]) for r in signals}
    if len(candidates)!=191 or len(bplus)!=11 or not bplus<=candidates:
        raise SystemExit("STOP: identity/coverage changed; expected 191 candidates, 11 B+ all in queue")
    print("F15 | F10 HISTORICAL STRICT-AND |",DAY)
    print("READ ONLY | NO API | NO B REPLAY | MARKET MINUTE != LIVE OBSERVED TIME")
    print("IDENTITY PASS | candidates",len(candidates),"formal B+",len(bplus),"non-B+",len(candidates-bplus))
    results=[];stops=[]
    with sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=5) as con:
        for s in sorted(candidates):
            rows=con.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<=? ORDER BY day DESC LIMIT 11",(s,DAY)).fetchall()
            if len(rows)!=11 or rows[0][0]!=DAY or len({r[0] for r in rows})!=11:
                stops.append((s,"missing today or 10 prior sessions"));continue
            today=rows[0]
            prior=list(reversed(rows[1:]))
            try:
                if any(r[0]>=DAY for r in prior):raise ValueError("future baseline")
                c_today=curve(today[2],today[1])
                hist=[curve(r[2],r[1]) for r in prior]
                fulls=[float(r[1]) for r in prior]
                denom5=sum(fulls[-5:])/5
                denom1=fulls[-1]
                if denom5<=0 or denom1<=0:raise ValueError("invalid denominator")
                first=None
                # Every trading minute, not only minutes with trades.
                for minute in range(9*60,13*60+31):
                    t=f"{minute//60:02d}:{minute%60:02d}:00"
                    v=at(c_today,t)
                    if v<1000:continue
                    f10=sum(at(c,t)/full for c,full in zip(hist,fulls))/10
                    if f10<=0:continue
                    projected=v/f10
                    e5=projected/denom5;e1=projected/denom1
                    if e5>=2.5 and e1>=2.5:
                        first=(t[:5],v,f10,e5,e1);break
                results.append((s,"B+" if s in bplus else "NON_BPLUS",first))
            except (ValueError,TypeError,IndexError,ZeroDivisionError) as e:
                stops.append((s,str(e)))
    if len(results)+len(stops)!=len(candidates):
        raise SystemExit("STOP: result identity mismatch")
    passed=[r for r in results if r[2]]
    print("VALID STOCKS",len(results),"STOPPED",len(stops))
    print("STRICT AND PASSED",len(passed),"B+",sum(r[1]=="B+" for r in passed),"NON_BPLUS",sum(r[1]=="NON_BPLUS" for r in passed))
    print("STRICT AND NOT PASSED",len(results)-len(passed))
    print("STOPPED STOCKS",stops)
    print("PASSING DETAILS | stock | formal | first minute | cumulative lots | F10 | EVG5 | EVG1")
    for s,group,x in sorted(passed,key=lambda r:(r[2][0],r[0])):
        print(s,group,x[0],f"{x[1]:.1f}",f"{x[2]:.6f}",f"{x[3]:.3f}",f"{x[4]:.3f}")
    print("CAUTION: NON_BPLUS includes B- and B-not-evaluated; this is not a B recognition result.")
    print("DONE | NO WRITES | NO NETWORK")

if __name__=="__main__":main()
