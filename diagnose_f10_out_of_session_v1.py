#!/usr/bin/env python3
"""Read-only diagnostic of F10 minute boundaries; no exclusion, no curve replay."""
import sqlite3,json,collections,datetime as dt
p="/var/data/stock-alert/backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3"
c=sqlite3.connect("file:"+p+"?mode=ro",uri=True)
days=[x[0] for x in c.execute("SELECT day FROM f10_day GROUP BY day HAVING COUNT(*)>=1400 ORDER BY day")]
if len(days)!=11:raise SystemExit("STOP: expected 11 broad-coverage days; got "+str(days))
def m(x):
 s=str(x).replace("T"," ").split()[-1][:5]
 try:
  t=dt.datetime.strptime(s,"%H:%M");return t.hour*60+t.minute
 except:raise SystemExit("STOP: unknown timestamp "+repr(x))
def fmt(t):return f"{t//60:02d}:{t%60:02d}"
print("DAY | ROWS | OUTSIDE_POINTS | OUTSIDE_STOCK_DAYS | EARLIEST | LATEST | EXAMPLES")
total=0
for day in days:
 outside=collections.Counter();examples=[];low=9999;high=-1;rows=0;affected=0
 for symbol,raw in c.execute("SELECT symbol,pts_json FROM f10_day WHERE day=?",(day,)):
  rows+=1;a=json.loads(raw)
  if not isinstance(a,list) or not a:raise SystemExit("STOP: missing pts "+day+" "+symbol)
  bad=False
  for x in a:
   if isinstance(x,(list,tuple)) and len(x)>=2:t=x[0]
   elif isinstance(x,dict):t=next((x[k] for k in ("minute","time","t","timestamp") if k in x),None)
   else:raise SystemExit("STOP: unsupported pts "+day+" "+symbol)
   if t is None:raise SystemExit("STOP: missing time "+day+" "+symbol)
   z=m(t);low=min(low,z);high=max(high,z)
   if z<540 or z>810:
    outside[fmt(z)]+=1;bad=True
    if len(examples)<6:examples.append((symbol,str(t)))
  affected+=int(bad)
 total+=sum(outside.values())
 print(day,rows,sum(outside.values()),affected,fmt(low),fmt(high),repr(examples))
 if outside:print("  OUTSIDE TIMES",outside.most_common(12))
print("TOTAL_OUTSIDE_POINTS",total)
print("DIAGNOSTIC ONLY: no F10 points changed or filtered.")
