#!/usr/bin/env python3
"""Independent F10 expansion smoke test. Never writes production F10 DB."""
import argparse,csv,hashlib,json,os,sqlite3,sys,time
from datetime import date,timedelta,datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from f10_baseline_store_v1 import fetch,parse
ROOT=Path("/var/data/stock-alert/_f10_expansion_research")
ROSTER=ROOT/"f10_expansion_roster_v1.json"
CSV=ROOT/"f10_expansion_add_1014_v1.csv"
STAGE=ROOT/"f10_expansion_stage_v1.sqlite3"
PROD=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
TZ=ZoneInfo("Asia/Taipei")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=5)
    p.add_argument("--pause",type=float,default=0.5)
    a=p.parse_args()
    if not 1<=a.limit<=10: raise RuntimeError("smoke test limit must be 1..10")
    if a.pause<0.25: raise RuntimeError("pause must be >=0.25")
    roster=json.loads(ROSTER.read_text(encoding="utf-8"))
    rows=list(csv.DictReader(CSV.open(encoding="utf-8-sig",newline="")))
    names=[r["symbol"] for r in rows]
    if roster.get("status")!="DRAFT - no production integration" or len(names)!=1014 or len(set(names))!=1014 or set(names)!=set(roster["new_symbols"]):
        raise RuntimeError("roster CSV/JSON identity mismatch")
    with sqlite3.connect(f"file:{PROD}?mode=ro",uri=True) as prod:
        existing={x[0] for x in prod.execute("SELECT symbol FROM member")}
    if existing.intersection(names): raise RuntimeError("production membership overlaps staged roster")
    key=os.environ.get("FUGLE_API_KEY","").strip()
    if not key: raise RuntimeError("FUGLE_API_KEY missing; no requests sent")
    now=datetime.now(TZ)
    end=(now.date() if (now.hour,now.minute)>=(14,30) else now.date()-timedelta(days=1))
    start=end-timedelta(days=24)
    if STAGE.resolve()==PROD.resolve(): raise RuntimeError("staging equals production")
    with sqlite3.connect(STAGE,timeout=20) as c:
        c.execute("CREATE TABLE IF NOT EXISTS f10_day(symbol TEXT NOT NULL,day TEXT NOT NULL,full REAL NOT NULL,pts_json TEXT NOT NULL,PRIMARY KEY(symbol,day))")
        c.execute("CREATE TABLE IF NOT EXISTS audit(symbol TEXT PRIMARY KEY,status TEXT NOT NULL,detail TEXT NOT NULL,checked_at TEXT NOT NULL)")
        c.commit()
        for i,s in enumerate(names[:a.limit],1):
            print(f"[FETCH] {i}/{a.limit} {s} {start}..{end}",flush=True)
            try:
                obj=fetch(s,start.isoformat(),end.isoformat(),key)
                days=parse(s,obj,end.isoformat())
                if len(days)<5: raise RuntimeError(f"valid sessions <5: {len(days)}")
                days=days[-11:]
                for day,full,pts in days:
                    if day> end.isoformat() or full<=0 or not pts or abs(pts[-1][1]-full)>0.0001:
                        raise RuntimeError("day volume integrity failed")
                with c:
                    c.execute("DELETE FROM f10_day WHERE symbol=?",(s,))
                    c.executemany("INSERT INTO f10_day VALUES(?,?,?,?)",[(s,d,v,json.dumps(pts,separators=(",",":"))) for d,v,pts in days])
                    c.execute("INSERT OR REPLACE INTO audit VALUES(?,?,?,?)",(s,"PASS",f"sessions={len(days)}",datetime.now(TZ).isoformat()))
                print(f"[PASS] {s} sessions={len(days)}",flush=True)
            except Exception as e:
                with c:
                    c.execute("INSERT OR REPLACE INTO audit VALUES(?,?,?,?)",(s,"FAIL",f"{type(e).__name__}: {e}",datetime.now(TZ).isoformat()))
                print(f"[FAIL] {s} {type(e).__name__}: {e}",flush=True)
            time.sleep(a.pause)
        summary=c.execute("SELECT status,COUNT(*) FROM audit GROUP BY status").fetchall()
    print("[STAGING ONLY]",STAGE,flush=True)
    print("[AUDIT]",summary,flush=True)
    print("[NO PRODUCTION WRITE] [NO A/B CHANGE]",flush=True)
if __name__=="__main__":
    try: main()
    except Exception as e:
        print(f"[STOP] {type(e).__name__}: {e}",file=sys.stderr,flush=True);sys.exit(2)
