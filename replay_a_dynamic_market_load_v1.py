#!/usr/bin/env python3
"""Exploratory F10 dynamic gate workload replay. Read-only, no production writes.
Sparse updates treated as observed cumulative volume; threshold evaluated at each minute
using latest observed value. No interpolation, no hindsight.
"""
import sqlite3,json,datetime as dt,collections,statistics,math
DB="/var/data/stock-alert/backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3"
def stop(x):raise SystemExit("STOP / FAIL CLOSED: "+str(x))
c=sqlite3.connect("file:"+DB+"?mode=ro",uri=True)
days=[x[0] for x in c.execute("SELECT day FROM f10_day GROUP BY day HAVING COUNT(*)>=1400 ORDER BY day")]
if len(days)!=11:stop("expected 11 broad coverage days")
def minute(v):
 s=str(v).replace("T"," ").split()[-1][:5]
 try:t=dt.datetime.strptime(s,"%H:%M");return t.hour*60+t.minute
 except:stop("bad timestamp "+str(v))
def parse(raw,d,s):
 a=json.loads(raw)
 if not isinstance(a,list) or not a:stop("empty "+d+" "+s)
 out=[]
 for p in a:
  if isinstance(p,(list,tuple)) and len(p)>=2:t,v=p[:2]
  elif isinstance(p,dict):
   t=next((p[k] for k in ("minute","time","t","timestamp") if k in p),None)
   v=next((p[k] for k in ("cumulative_volume_zhang","cum","volume","v") if k in p),None)
  else:stop("bad point "+d+" "+s)
  if t is None or v is None:stop("missing fields "+d+" "+s)
  t=minute(t);v=float(v)
  if not math.isfinite(v) or v<0:stop("bad volume "+d+" "+s)
  out.append((t,v))
 if any(out[i][0]>=out[i+1][0] or out[i][1]>out[i+1][1]+1e-8 for i in range(len(out)-1)):stop("order/volume "+d+" "+s)
 if any((t<540 or t>810) for t,v in out) and s!="6604":stop("unexpected session "+d+" "+s)
 return [(t,v) for t,v in out if 540<=t<=810]
# Illustrative 09:00 2000 lots -> 13:30 800 lots, same as previous B-event test.
def threshold(t,shape):
 x=max(0,min(1,(t-540)/270))
 f={"linear":x,"early":1-(1-x)**2,"late":x*x}[shape]
 return 2000-1200*f
shapes=("linear","early","late")
byday=collections.defaultdict(lambda:collections.defaultdict(list))
print("METHOD: evaluate at minute t+1 after completed F10 observation at t; sparse volume carried forward.")
print("LIMIT: F10 universe may be selected; missing updates could make crossings late; no B capacity measured.")
for d in days:
 seen=set()
 for s,raw in c.execute("SELECT symbol,pts_json FROM f10_day WHERE day=?",(d,)):
  if s in seen:stop("duplicate "+d+" "+s)
  seen.add(s)
  pts=parse(raw,d,s)
  # Strictly causal: at decision minute m, only F10 observations with t<m are available.
  for shape in shapes:
   j=0;volume=None;hit=None
   for m in range(541,811):
    while j<len(pts) and pts[j][0]<m:
     volume=pts[j][1];j+=1
    if volume is not None and volume>=threshold(m,shape):
     hit=m;break
   if hit is not None:byday[d][shape].append((s,hit))
 if not (1400<=len(seen)<=1500):stop("unexpected daily stock coverage "+d)
print("DAY | LINEAR | EARLY | LATE | EARLY_PEAK_1MIN | EARLY_PEAK_5MIN | EARLY_BEFORE_1000")
for d in days:
 v=byday[d]
 minutes=[t for s,t in v["early"]]
 ctr=collections.Counter(minutes)
 peak=max(ctr.values(),default=0)
 peak5=max((sum(ctr[m+i] for i in range(5)) for m in range(541,807)),default=0)
 print(d,len(v["linear"]),len(v["early"]),len(v["late"]),peak,peak5,sum(t<=600 for t in minutes))
print("TOTALS",*(sum(len(byday[d][s]) for d in days) for s in shapes))
print("CAUTION: results are gate workload candidates, not B calls, trend recognitions, or notifications.")
