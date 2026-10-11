#!/usr/bin/env python3
"""Historical official-function VCP replay for B-signal stock-days. READ ONLY."""
import ast
import copy
import json
import math
import sqlite3
from pathlib import Path
from collections import Counter

SRC=Path("/opt/render/project/src/fugle_a_scanner_v2_4.py")
DB=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
ROOT=Path("/var/data/stock-alert/b_live_runner_v2_p1")
LIMITS=(0,500,800,1000,2000)
START="2026-09-29"
END="2026-10-08"

def fail(msg):
    raise RuntimeError("STOP: "+msg)

def official_function():
    tree=ast.parse(SRC.read_text(encoding="utf-8"))
    classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="StrongSelector"]
    if len(classes)!=1: fail("selector identity")
    helpers={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ("sd_of","safe_max")}
    methods=[n for n in classes[0].body if isinstance(n,ast.FunctionDef) and n.name=="analyze_vcp"]
    if set(helpers)!={"sd_of","safe_max"} or len(methods)!=1: fail("VCP function identity")
    fn=copy.deepcopy(methods[0]); fn.decorator_list=[]
    mod=ast.Module(body=[copy.deepcopy(helpers["sd_of"]),copy.deepcopy(helpers["safe_max"]),fn],type_ignores=[])
    ast.fix_missing_locations(mod)
    ns={"math":math,"List":list,"Dict":dict,"Any":object}
    exec(compile(mod,str(SRC),"exec"),ns)
    return ns["analyze_vcp"]

class Isolated:
    track_path=None
    def __init__(self,fn):
        self.track={}
        self.analyze_vcp=fn.__get__(self,Isolated)

def main():
    print("OFFICIAL VCP B-SIGNAL COHORT | READ ONLY | NO API | NO PRODUCTION WRITE")
    for p in (SRC,DB,ROOT):
        if not p.exists(): fail("missing "+str(p))
    fn=official_function()
    cohort=[]
    for daydir in sorted(ROOT.iterdir()):
        if not daydir.is_dir() or not (START<=daydir.name<=END): continue
        for sd in sorted(daydir.iterdir()):
            if not sd.is_dir(): continue
            if not ((sd/"signal_event.json").is_file() or (sd/"p1_signal_event.json").is_file()): continue
            f=sd/"canonical_minutes.jsonl"
            if not f.is_file(): fail("signal missing minutes "+str(sd))
            cohort.append((daydir.name,sd.name,f))
    if len(cohort)!=183: fail("cohort identity count="+str(len(cohort))+" expected=183")
    print("COHORT_IDENTITY:",len(cohort))
    records=[]; skipped=[]
    con=sqlite3.connect(f"file:{DB}?mode=ro",uri=True)
    try:
        for day,sid,path in cohort:
            hist=con.execute("SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 65",(sid,day)).fetchall()
            hist.reverse()
            if len(hist)<60:
                skipped.append((day,sid,len(hist)))
                continue
            if len(set(x[0] for x in hist))!=len(hist) or any(x[0]>=day or x[1] is None or float(x[1])<=0 or x[2] is None or float(x[2])<0 for x in hist):
                fail("daily identity "+day+" "+sid)
            rows=[json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
            if not rows: fail("empty minutes "+day+" "+sid)
            times=[r["minute"] for r in rows]
            if times!=sorted(set(times)): fail("minute ordering "+day+" "+sid)
            for r in rows:
                if r.get("date")!=day or str(r.get("stock_id"))!=sid or float(r["close"])<=0 or float(r["volume"])<0:
                    fail("minute identity "+day+" "+sid)
            selector=Isolated(fn)
            dates=[x[0] for x in hist]; closes=[float(x[1]) for x in hist]; vols=[float(x[2]) for x in hist]
            cumulative=0.0; first={}; new_events=0
            for r in rows:
                cumulative+=float(r["volume"])
                v=selector.analyze_vcp(closes+[float(r["close"])],vols+[cumulative],sid,dates+[day])
                track=v.get("breakoutTrack") or {}
                fresh=track.get("isNew") is True and track.get("dayCount")==1 and not track.get("broken")
                active=track.get("dayCount")==1 and not track.get("broken")
                if fresh:
                    new_events+=1
                    first.setdefault("NEW",r["minute"])
                if active:
                    for t in LIMITS:
                        if cumulative>=t: first.setdefault(str(t),r["minute"])
            records.append((day,sid,first,new_events))
    finally:
        con.close()
    if len(records)!=182 or skipped!=[("2026-10-08","4171",0)]:
        fail("coverage mismatch valid="+str(len(records))+" skipped="+str(skipped))
    print("COVERAGE_PASS: valid=182 excluded="+str(skipped))
    print("METHOD: original VCP function; SQLite historical daily + canonical minute increments; fresh in-memory track per stock-day")
    print("NOTE: B-signal-selected cohort, not all-market; A historical source and persistent track may differ")
    fresh=[r for r in records if "NEW" in r[2]]
    print("FRESH_NEW_VCP_COUNT:",len(fresh),"OUT_OF",len(records))
    for t in LIMITS:
        key=str(t)
        eligible=[r for r in records if key in r[2]]
        delayed=[r for r in eligible if r[2][key]>r[2].get("0","99:99:99")]
        never=[r for r in records if "0" in r[2] and key not in r[2]]
        gaps=[]
        for r in delayed:
            def sec(s):
                h,m,s=map(int,s.split(":")); return 3600*h+60*m+s
            gaps.append((sec(r[2][key])-sec(r[2]["0"]))//60)
        gaps.sort()
        med=gaps[len(gaps)//2] if gaps else 0
        print("THRESHOLD",t,"ELIGIBLE",len(eligible),"DELAYED",len(delayed),"NEVER_AFTER_VCP",len(never),"DELAY_MED_MIN",med,"DELAY_MAX_MIN",max(gaps,default=0))
    print("CASE_ROWS (day stock new vcp 500 800 1000 2000):")
    for r in records:
        if r[1] in ("6175","3236") and r[0]=="2026-10-01":
            print(r[0],r[1],*[r[2].get(k,"-") for k in ("NEW","0","500","800","1000","2000")])
    print("FIRST_25_VCP_ROWS (day stock new vcp 800 2000):")
    for r in [x for x in records if "0" in x[2]][:25]:
        print(r[0],r[1],*[r[2].get(k,"-") for k in ("NEW","0","800","2000")])
    print("TIMELINE_25 | DATE STOCK VCP_TIME VCP_PCT P1_TIME P1_PCT BUY_TIME BUY_PCT DAY_CLOSE_PCT ORDER")
    counts=Counter()
    with sqlite3.connect(f"file:{DB}?mode=ro",uri=True) as c:
        for day,sid,first,events in records:
            if "NEW" not in first: continue
            p=ROOT/day/sid
            sig=p/"p1_signal_event.json"
            vcp=first["NEW"]
            rs=[json.loads(x) for x in (p/"canonical_minutes.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
            by={r["minute"]:r for r in rs}
            prior=c.execute("SELECT day,close FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 1",(sid,day)).fetchone()
            today=c.execute("SELECT close FROM daily_ohlcv WHERE symbol=? AND day=?",(sid,day)).fetchone()
            if not prior or not today or float(prior[1])<=0: fail("daily close missing "+day+" "+sid)
            if vcp not in by: fail("VCP minute missing "+day+" "+sid)
            base=float(prior[1]); pct=lambda x:round((float(x)/base-1)*100,2)
            if not sig.is_file():
                counts["NO_P1_RECORD"]+=1
                print(day,sid,vcp,pct(by[vcp]["close"]),"-","-","-","-",pct(today[0]),"NO_P1_RECORD")
                continue
            d=json.loads(sig.read_text(encoding="utf-8"))
            if str(d.get("stock_id"))!=sid or d.get("date")!=day: fail("P1 identity "+day+" "+sid)
            rec=d.get("recognition_time")
            if rec not in by: fail("P1 minute missing "+day+" "+sid+" "+str(rec))
            nxt=next((r for r in rs if r["minute"]>max(vcp,rec)),None)
            if nxt is None: fail("no post-confirmation minute "+day+" "+sid)
            order="VCP_FIRST" if vcp<rec else ("P1_FIRST" if rec<vcp else "SAME")
            counts[order]+=1
            print(day,sid,vcp,pct(by[vcp]["close"]),rec,pct(by[rec]["close"]),nxt["minute"],pct(nxt["open"]),pct(today[0]),order)
    print("SUMMARY",dict(counts),"TOTAL",sum(counts.values()))
    if sum(counts.values())!=25: fail("timeline cohort mismatch")
    print("STATUS: PASS_TIMELINE_25")
    print("STATUS: PASS_RESEARCH_ONLY")

if __name__=="__main__":
    main()
