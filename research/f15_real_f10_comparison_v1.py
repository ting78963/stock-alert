#!/usr/bin/env python3
"""F15 real F10 data audit, read-only. Independent curve comparison with production A semantics."""
import argparse,bisect,datetime as dt,json,math,os,sqlite3,sys
from pathlib import Path
DEFAULT="/var/data/stock-alert/f10_baseline_v1.sqlite3"
def checked(rows,cut):
 if len(rows)!=10:raise ValueError("F10_INCOMPLETE")
 days=[];last_date=""
 for ds,full,raw in rows:
  if ds<=last_date:raise ValueError("NONINCREASING_DATES")
  last_date=ds
  full=float(full)
  if not math.isfinite(full) or full<=0:raise ValueError("INVALID_FULL")
  pts=json.loads(raw)
  if not isinstance(pts,list) or not pts:raise ValueError("EMPTY_POINTS")
  times=[];vals=[]
  for item in pts:
   if not isinstance(item,list) or len(item)!=2:raise ValueError("BAD_POINT")
   t,v=str(item[0]),float(item[1])
   if len(t)!=8 or (times and t<=times[-1]) or not math.isfinite(v) or v<0 or (vals and v<vals[-1]):raise ValueError("BAD_CURVE")
   times.append(t);vals.append(v)
  if abs(vals[-1]-full)>1e-9:raise ValueError("FULL_MISMATCH")
  days.append((ds,full,times,vals))
 fulls=[d[1] for d in days]
 cut=cut if len(cut)==8 else cut+":00"
 # Reference: union of all historical 1-minute time stamps, exactly as A constructs the curve.
 cutoffs=sorted({t for _,_,ts,_ in days for t in ts})
 fractions_by_cut={}
 for t in cutoffs:
  frac=0.
  for _,full,ts,vs in days:
   i=bisect.bisect_right(ts,t)-1
   frac+=(vs[i] if i>=0 else 0.)/full
  fractions_by_cut[t]=frac/10
 i=bisect.bisect_right(cutoffs,cut)-1
 reference=fractions_by_cut[cutoffs[i]] if i>=0 else 0.
 # Independent direct computation at query cutoff.
 direct=sum((d[3][bisect.bisect_right(d[2],cut)-1] if bisect.bisect_right(d[2],cut) else 0.)/d[1] for d in days)/10
 if not (math.isfinite(reference) and reference>0):raise ValueError("INVALID_F10_CUTOFF")
 if abs(reference-direct)>1e-12:raise ValueError("REFERENCE_MISMATCH")
 return reference, sum(fulls[-5:])/5,fulls[-1],days
def main():
 p=argparse.ArgumentParser();p.add_argument("--db",default=DEFAULT);p.add_argument("--date",default=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat());p.add_argument("--minute",default="09:30");p.add_argument("--limit",type=int,default=25);a=p.parse_args()
 print("F15 | REAL F10 READONLY COMPARISON V1")
 print("NO API | NO A/B IMPORT | NO WRITES | NO LIVE CLAIM")
 try:dt.date.fromisoformat(a.date);dt.time.fromisoformat(a.minute)
 except ValueError:raise SystemExit("AUDIT STOP: invalid date/minute")
 if a.limit<1 or a.limit>100:raise SystemExit("AUDIT STOP: limit 1..100")
 db=Path(a.db)
 if not db.is_file():raise SystemExit("AUDIT STOP: database missing "+str(db))
 uri="file:"+str(db.resolve())+"?mode=ro"
 con=sqlite3.connect(uri,uri=True,timeout=5)
 try:
  con.execute("PRAGMA query_only=ON")
  table=con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='f10_day'").fetchone()
  if not table:raise SystemExit("AUDIT STOP: f10_day missing")
  total=con.execute("SELECT COUNT(DISTINCT symbol) FROM f10_day WHERE day<?",(a.date,)).fetchone()[0]
  syms=[r[0] for r in con.execute("SELECT symbol FROM f10_day WHERE day<? GROUP BY symbol HAVING COUNT(*)>=10 ORDER BY symbol LIMIT ?",(a.date,a.limit)).fetchall()]
  print("DB",db,"DATE",a.date,"CUTOFF",a.minute,"SYMBOLS_WITH_HISTORY",total,"SAMPLE",len(syms))
  ok=0;bad=0
  for sym in syms:
   rows=con.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(sym,a.date)).fetchall()[::-1]
   try:
    f,avg,prev,days=checked(rows,a.minute)
    if days[-1][0]>=a.date:raise ValueError("FUTURE_LEAK")
    print("PASS",sym,"DAYS",days[0][0],days[-1][0],"F10",round(f,8),"AVG5",round(avg,3),"PREV1",round(prev,3))
    ok+=1
   except Exception as e:
    print("STOP",sym,type(e).__name__,str(e)[:90]);bad+=1
  print("SUMMARY",f"PASS={ok}",f"STOP={bad}",f"AVAILABLE={total}")
  if not syms:raise SystemExit("AUDIT STOP: no symbols with >=10 historical sessions")
  if bad:raise SystemExit("AUDIT STOP: invalid sampled F10 rows")
  print("REFERENCE VS DIRECT F10 MATCH | HISTORICAL BASELINE VERIFIED")
  print("NOT YET VERIFIED: production live snapshot timestamps, real-time EVG values, or shadow capture")
 finally:con.close()
if __name__=="__main__":main()
