#!/usr/bin/env python3
"""A gate integration research: D5 vs early-decline curves, read-only, no production modifications."""
import sqlite3,json,math,datetime as dt,collections,statistics
DB="/var/data/stock-alert/backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3"
def stop(x):raise SystemExit("STOP / FAIL CLOSED: "+str(x))
c=sqlite3.connect("file:"+DB+"?mode=ro",uri=True)
days=[d for (d,) in c.execute("SELECT day FROM f10_day GROUP BY day HAVING COUNT(*)>=1400 ORDER BY day")]
if len(days)!=11:stop("expected 11 days")
def minute(t):
 try:
  x=dt.datetime.strptime(str(t).replace("T"," ").split()[-1][:5],"%H:%M")
  return x.hour*60+x.minute
 except:stop("bad time "+str(t))
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
  if not math.isfinite(v) or v<0:stop("invalid volume "+d+" "+s)
  out.append((t,v))
 if any(out[i][0]>=out[i+1][0] or out[i][1]>out[i+1][1]+1e-8 for i in range(len(out)-1)):stop("nonmonotone "+d+" "+s)
 if any(t<540 or t>810 for t,v in out) and s!="6604":stop("unexpected after-hours "+d+" "+s)
 return [(t,v) for t,v in out if 540<=t<=810]
# Same floor of 1000 for comparable workload; endpoint hypotheses NOT fitted.
# Avoid 09:10 step by continuous interpolation from opening Y at 09:09.
# Compare x/y historical candidate vs legacy D5 and two continuous shapes.
cfgs=("D5","C3000_4000","C4000_4000","C3000_3000")
def gate(m,k):
 if k=="D5":
  if m<=549:return 4000
  return max(1000,2000-((m-540)//10)*300)
 x,y={"C3000_4000":(3000,4000),"C4000_4000":(4000,4000),"C3000_3000":(3000,3000)}[k]
 if m<=544:return x
 if m<=549:return y
 # from 09:10 toward 1000 at 13:30, faster early decline, continuous at 09:09
 z=(m-549)/261
 return 1000+(y-1000)*(1-z)**2
results=collections.defaultdict(lambda:collections.defaultdict(list))
for d in days:
 seen=set()
 for s,raw in c.execute("SELECT symbol,pts_json FROM f10_day WHERE day=?",(d,)):
  if s in seen:stop("duplicate "+d+" "+s)
  seen.add(s);pts=parse(raw,d,s)
  for k in cfgs:
   j=0;v=None
   for m in range(541,811):
    while j<len(pts) and pts[j][0]<m:v=pts[j][1];j+=1
    if v is not None and v>=gate(m,k):
     results[d][k].append((s,m));break
 if not 1400<=len(seen)<=1500:stop("coverage "+d)
print("AUDIT PASS | 11 days | read only | F10 observed bars available from next minute")
print("CAUTION: sparse updates treated as carried cumulative volume; semantics and full market coverage unverified.")
print("CURVE | TOTAL | DAILY_AVG | MAX_1MIN | MAX_5MIN | MAX_AT_0910 | FIRST_BEFORE_0930")
for k in cfgs:
 allhits=[(d,s,m) for d in days for s,m in results[d][k]]
 ctr=collections.Counter((d,m) for d,s,m in allhits)
 peak=max(ctr.values(),default=0)
 peak5=max((sum(ctr[d,m+i] for i in range(5)) for d in days for m in range(541,807)),default=0)
 print(k,len(allhits),round(len(allhits)/11,1),peak,peak5,max((ctr[d,550] for d in days),default=0),sum(m<=570 for d,s,m in allhits))
print("DAY | "+ " | ".join(cfgs))
for d in days:print(d,*[len(results[d][k]) for k in cfgs])
print("NOTE: exploratory comparison, not B processing cost or recognition accuracy. No production changes.")
