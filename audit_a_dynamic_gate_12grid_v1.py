#!/usr/bin/env python3
"""A dynamic gate parameter study v1: F10 market workload, strictly read-only.
No returns, no network, no LINE, no production writes. Threshold choices are predeclared.
Not a measure of B actual API cost or B recognition.
"""
import collections,datetime as dt,json,math,sqlite3,statistics,sys
DB="/var/data/stock-alert/backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3"
def fail(msg):raise SystemExit("STOP / FAIL CLOSED: "+str(msg))
try: conn=sqlite3.connect("file:"+DB+"?mode=ro",uri=True)
except Exception as e:fail(e)
days=[r[0] for r in conn.execute("SELECT day FROM f10_day GROUP BY day HAVING COUNT(*)>=1400 ORDER BY day")]
if len(days)!=11:fail("expected 11 broad-coverage days, found "+str(days))
def parse(raw,day,sym):
 try:a=json.loads(raw)
 except Exception as e:fail(f"{day}/{sym}: JSON {e}")
 if not isinstance(a,list) or not a:fail(f"{day}/{sym}: no F10 points")
 out=[];last_stamp=-1;last_vol=-1
 for p in a:
  if not isinstance(p,(list,tuple)) or len(p)<2:fail(f"{day}/{sym}: bad point")
  t=str(p[0])
  try:
   h,m,sec=map(int,t[:8].split(":"));stamp=h*3600+m*60+sec
   v=float(p[1])
  except Exception as e:fail(f"{day}/{sym}: invalid time/volume {e}")
  if not (0<=h<24 and 0<=m<60 and 0<=sec<60) or not math.isfinite(v) or v<0 or stamp<=last_stamp:fail(f"{day}/{sym}: invalid ordering/volume")
  last_stamp=stamp
  if 540<=h*60+m<=810:
   if v<last_vol:fail(f"{day}/{sym}: falling cumulative volume")
   last_vol=v;out.append((h*60+m,v))
 if not out:fail(f"{day}/{sym}: no regular-session points")
 return out
# Curves: 09:01-04 X=3000, 09:05-09 Y=4000, latched after first crossing.
# Smooth 09:10-09:30 to target with quadratic early decline, then 09:30-13:30 to floor.
# No threshold step at 09:10 or 09:30. Slope may change at 09:30.
cfgs=[("D5",None,None),("PREV",None,None)]+[(f"T{target}_F{floor}",target,floor) for target in (1700,2000,2300,2600) for floor in (800,1000,1200)]
def gate(m,k,target,floor):
 if k=="D5":
  if m<=549:return 4000
  return max(1000,2000-((m-540)//10)*300)
 if k=="PREV":
  if m<=544:return 3000
  if m<=549:return 4000
  z=(m-549)/261
  return 1000+3000*(1-z)**2
 if m<=544:return 3000
 if m<=549:return 4000
 if m<=570:
  z=(m-549)/21
  return target+(4000-target)*(1-z)**2
 z=(m-570)/240
 return floor+(target-floor)*(1-z)**2
results=collections.defaultdict(dict)
total_rows=0
for day in days:
 seen=set(); rows=conn.execute("SELECT symbol,pts_json FROM f10_day WHERE day=? ORDER BY symbol",(day,)).fetchall()
 if len(rows)<1400:fail("insufficient coverage "+day)
 for sym,raw in rows:
  if sym in seen:fail("duplicate "+day+"/"+sym)
  seen.add(sym);total_rows+=1;pts=parse(raw,day,sym)
  hits={k:None for k,_,_ in cfgs};i=0;vol=None
  for m in range(541,811):
   while i<len(pts) and pts[i][0]+1<=m:vol=pts[i][1];i+=1
   if vol is None:continue
   for k,t,f in cfgs:
    if hits[k] is None and vol>=gate(m,k,t,f):hits[k]=m
  results[day][sym]=hits
print(f"AUDIT PASS | days={len(days)} stock_days={total_rows} | READ ONLY")
print("CAUTION: F10 sparse minutes use last observed cumulative volume; bar minute+1 assumed; neither independently verified.")
print("CAUTION: threshold-only first eligibility, not actual B handoffs, recognition, or API throughput.")
print("CONFIG TOTAL AVG_DAY PEAK_1MIN PEAK_5MIN PEAK_0910 BEFORE_0930 MED_FIRST_MIN D5_EARLIER D5_LATER D5_SAME")
for k,t,f in cfgs:
 counts=collections.Counter();first=[];earlier=later=same=0
 for day,stocks in results.items():
  for sym,hits in stocks.items():
   m=hits[k];base=hits["D5"]
   if m is None:continue
   counts[day,m]+=1;first.append(m)
   if k!="D5" and base is not None:
    if m<base:earlier+=1
    elif m>base:later+=1
    else:same+=1
 peak=max(counts.values(),default=0)
 peak5=max((sum(counts[d,m+i] for i in range(5)) for d in days for m in range(541,807)),default=0)
 at10=max((counts[d,550] for d in days),default=0)
 before=sum(m<=570 for m in first)
 print(k,len(first),round(len(first)/len(days),1),peak,peak5,at10,before,round(statistics.median(first),1) if first else "-",earlier,later,same)
print("DAY COUNTS:")
print("DAY "+" ".join(k for k,_,_ in cfgs))
for d in days:
 print(d,*[sum(v[k] is not None for v in results[d].values()) for k,_,_ in cfgs])
print("PASS | Research only | No parameter selection based on future returns")
