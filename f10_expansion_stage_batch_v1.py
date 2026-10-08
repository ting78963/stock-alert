#!/usr/bin/env python3
"""Resumable F10 expansion staging. No production DB writes, no A/B changes."""
import argparse,csv,json,os,sqlite3,sys,time,urllib.error
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from f10_baseline_store_v1 import fetch,parse
ROOT=Path("/var/data/stock-alert/_f10_expansion_research")
ROSTER=ROOT/"f10_expansion_roster_v1.json"
CSV=ROOT/"f10_expansion_add_1014_v1.csv"
STAGE=ROOT/"f10_expansion_stage_v1.sqlite3"
PROD=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
TZ=ZoneInfo("Asia/Taipei")
EXCLUDED={"1589"}  # User-approved delisted candidate; preserve frozen audit for traceability
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--batch",type=int,default=30)
    ap.add_argument("--pause",type=float,default=0.75)
    ap.add_argument("--retry-failed",action="store_true")
    args=ap.parse_args()
    if not 1<=args.batch<=300 or args.pause<0.5: raise RuntimeError("batch must be 1..300 and pause >=0.5s")
    roster=json.loads(ROSTER.read_text(encoding="utf-8"))
    with CSV.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
    names=[r["symbol"] for r in rows]
    if roster.get("status")!="DRAFT - no production integration" or len(names)!=1014 or len(set(names))!=1014 or set(names)!=set(roster["new_symbols"]):
        raise RuntimeError("frozen roster mismatch; STOP")
    with sqlite3.connect(f"file:{PROD}?mode=ro",uri=True) as prod:
        existing={r[0] for r in prod.execute("SELECT symbol FROM member")}
    if existing.intersection(names): raise RuntimeError("roster overlaps production members; STOP")
    key=os.environ.get("FUGLE_API_KEY","").strip()
    if not key: raise RuntimeError("FUGLE_API_KEY missing")
    now=datetime.now(TZ)
    end=(now.date() if (now.hour,now.minute)>=(14,30) else now.date()-timedelta(days=1))
    start=end-timedelta(days=24)
    if STAGE.resolve()==PROD.resolve(): raise RuntimeError("staging path equals production")
    with sqlite3.connect(STAGE,timeout=30) as c:
        c.execute("CREATE TABLE IF NOT EXISTS f10_day(symbol TEXT NOT NULL,day TEXT NOT NULL,full REAL NOT NULL,pts_json TEXT NOT NULL,PRIMARY KEY(symbol,day))")
        c.execute("CREATE TABLE IF NOT EXISTS audit(symbol TEXT PRIMARY KEY,status TEXT NOT NULL,detail TEXT NOT NULL,checked_at TEXT NOT NULL)")
        c.commit()
        statuses={s:status for s,status in c.execute("SELECT symbol,status FROM audit")}
        if set(statuses)-set(names): raise RuntimeError("stage contains symbols outside roster; STOP")
        if not args.retry_failed:
            pending=[s for s in names if s not in statuses and s not in EXCLUDED]
        else:
            pending=[s for s in names if statuses.get(s)=="FAIL" and s not in EXCLUDED]
        selected=pending[:args.batch]
        print(f"[PLAN] total={len(names)} pass={sum(v=='PASS' for v in statuses.values())} fail={sum(v=='FAIL' for v in statuses.values())} pending={len([s for s in names if s not in statuses])} excluded={sorted(EXCLUDED)} selected={len(selected)} range={start}..{end}",flush=True)
        if not selected:
            print("[NO WORK] no matching symbols",flush=True);return
        consecutive_429=0
        for i,s in enumerate(selected,1):
            print(f"[FETCH] {i}/{len(selected)} {s}",flush=True)
            error=None
            for attempt in range(1,4):
                try:
                    obj=fetch(s,start.isoformat(),end.isoformat(),key)
                    days=parse(s,obj,end.isoformat())[-11:]
                    if len(days)<5: raise RuntimeError(f"valid sessions <5: {len(days)}")
                    for day,full,pts in days:
                        if day>end.isoformat() or full<=0 or not pts or abs(pts[-1][1]-full)>0.0001: raise RuntimeError("volume integrity mismatch")
                    with c:
                        c.execute("DELETE FROM f10_day WHERE symbol=?",(s,))
                        c.executemany("INSERT INTO f10_day VALUES(?,?,?,?)",[(s,d,v,json.dumps(pts,separators=(",",":"))) for d,v,pts in days])
                        c.execute("INSERT OR REPLACE INTO audit VALUES(?,?,?,?)",(s,"PASS",f"sessions={len(days)};end={end}",datetime.now(TZ).isoformat()))
                    print(f"[PASS] {s} sessions={len(days)}",flush=True);error=None;consecutive_429=0;break
                except Exception as e:
                    error=f"{type(e).__name__}: {e}"
                    if attempt<3:
                        is429=isinstance(e,urllib.error.HTTPError) and e.code==429
                        wait=(30*attempt if is429 else 5*attempt)
                        print(f"[RETRY] {s} attempt={attempt} wait={wait}s reason={error}",flush=True)
                        time.sleep(wait)
            if error is not None:
                with c:
                    c.execute("INSERT OR REPLACE INTO audit VALUES(?,?,?,?)",(s,"FAIL",error,datetime.now(TZ).isoformat()))
                print(f"[FAIL] {s} {error}",flush=True)
                if "HTTP Error 429" in error:
                    consecutive_429+=1
                    if consecutive_429>=2:
                        print("[COOLDOWN STOP] 2 consecutive 429 failures; preserve remaining pending symbols for later",flush=True)
                        break
                else:
                    consecutive_429=0
            time.sleep(args.pause)
        summary=c.execute("SELECT status,COUNT(*) FROM audit GROUP BY status").fetchall()
        rows_count=c.execute("SELECT COUNT(*) FROM f10_day").fetchone()[0]
    print(f"[SUMMARY] {summary} staged_day_rows={rows_count} stage={STAGE}",flush=True)
    print("[NO PRODUCTION WRITE] [NO A/B CHANGE]",flush=True)
if __name__=="__main__":
    try:main()
    except Exception as e:
        print(f"[STOP] {type(e).__name__}: {e}",file=sys.stderr,flush=True);sys.exit(2)
