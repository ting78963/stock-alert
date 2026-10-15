#!/usr/bin/env python3
"""Read-only F10 coverage audit v1.1: validate full points; report regular-session coverage separately."""
import sqlite3,json,datetime as dt,statistics,collections
DB="/var/data/stock-alert/backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3"
def stop(s):raise SystemExit("STOP / FAIL CLOSED: "+str(s))
c=sqlite3.connect("file:"+DB+"?mode=ro",uri=True)
if not {"symbol","day","pts_json"}.issubset({r[1] for r in c.execute("PRAGMA table_info(f10_day)") }):stop("unexpected schema")
dates=[r[0] for r in c.execute("SELECT day FROM f10_day GROUP BY day HAVING COUNT(*)>=1400 ORDER BY day")]
if len(dates)!=11:stop("expected 11 days "+repr(dates))
def tm(v):
 s=str(v).replace("T"," ").split()[-1][:5]
 try:t=dt.datetime.strptime(s,"%H:%M");return t.hour*60+t.minute
 except:stop("invalid timestamp "+repr(v))
def fmt(t):return f"{int(t)//60:02d}:{int(t)%60:02d}"
def parse(raw,day,sym):
 try:a=json.loads(raw)
 except:stop("bad JSON "+day+" "+sym)
 if not isinstance(a,list) or not a:stop("empty points "+day+" "+sym)
 out=[]
 for p in a:
  if isinstance(p,(list,tuple)) and len(p)>=2:t,v=p[0],p[1]
  elif isinstance(p,dict):
   t=next((p[k] for k in ("minute","time","t","timestamp") if k in p),None)
   v=next((p[k] for k in ("cumulative_volume_zhang","cum","volume","v") if k in p),None)
  else:stop("bad point "+day+" "+sym)
  if t is None or v is None:stop("missing point fields "+day+" "+sym)
  try:z=float(v)
  except:stop("bad volume "+day+" "+sym)
  if not (0<=z<float("inf")):stop("invalid volume "+day+" "+sym)
  out.append((tm(t),z))
 if any(out[i][0]>=out[i+1][0] or out[i][1]>out[i+1][1]+1e-8 for i in range(len(out)-1)):stop("time order or cumulative volume invalid "+day+" "+sym)
 return out
print("DAY | ROWS | MEDIAN_PTS | MIN_PTS | P10_PTS | MEDIAN_FIRST | MEDIAN_LAST | FIRST_AFTER_0910 | LAST_BEFORE_1300 | OUTSIDE_STOCK_DAYS | OUTSIDE_POINTS")
for day in dates:
 lengths=[];first=[];last=[];late=0;earlyend=0;outside_rows=0;outside_pts=0;seen=set()
 for sym,raw in c.execute("SELECT symbol,pts_json FROM f10_day WHERE day=?",(day,)):
  if sym in seen:stop("duplicate "+day+" "+sym)
  seen.add(sym)
  allpts=parse(raw,day,sym)
  outside=[t for t,v in allpts if not 540<=t<=810]
  if outside and sym!="6604":stop("unexpected out-of-session stock "+day+" "+sym)
  outside_rows+=bool(outside);outside_pts+=len(outside)
  pts=[(t,v) for t,v in allpts if 540<=t<=810]
  if not pts:stop("no regular session points "+day+" "+sym)
  lengths.append(len(pts));first.append(pts[0][0]);last.append(pts[-1][0])
  late+=pts[0][0]>550;earlyend+=pts[-1][0]<780
 lengths.sort()
 print(day,len(lengths),statistics.median(lengths),lengths[0],lengths[int((len(lengths)-1)*.1)],fmt(statistics.median(first)),fmt(statistics.median(last)),late,earlyend,outside_rows,outside_pts)
print("AUDIT PASS: full sequence validated; regular-session coverage reported; no original rows modified.")
print("IMPORTANT: gaps and missing quiet minutes require interpretation before first-crossing workload estimates.")
