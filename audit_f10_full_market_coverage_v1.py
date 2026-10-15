#!/usr/bin/env python3
"""F10 full-market coverage audit; strictly read-only, no curve interpretation."""
import sqlite3,json,collections,datetime as dt,statistics
from pathlib import Path
DB=Path("/var/data/stock-alert/backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3")
def stop(s):raise SystemExit("STOP / FAIL CLOSED: "+str(s))
if not DB.is_file():stop("database missing")
c=sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True)
schema={x[1] for x in c.execute("PRAGMA table_info(f10_day)")}
if not {"symbol","day","pts_json"}.issubset(schema):stop("schema mismatch "+str(schema))
def minute(v):
 s=str(v).replace("T"," ").split()[-1][:5]
 try:
  t=dt.datetime.strptime(s,"%H:%M");return t.hour*60+t.minute
 except:stop("invalid minute "+str(v))
def parse(raw):
 a=json.loads(raw)
 if not isinstance(a,list) or not a:stop("empty points")
 out=[]
 for p in a:
  if isinstance(p,(list,tuple)) and len(p)>=2:t,v=p[0],p[1]
  elif isinstance(p,dict):
   t=next((p[k] for k in ("minute","time","t","timestamp") if k in p),None)
   v=next((p[k] for k in ("cumulative_volume_zhang","cum","volume","v") if k in p),None)
  else:stop("unsupported point")
  if t is None or v is None:stop("missing minute or volume")
  out.append((minute(t),float(v)))
 if any(out[i][0]>=out[i+1][0] or out[i][1]>out[i+1][1]+1e-8 for i in range(len(out)-1)):stop("unordered time or falling cumulative volume")
 if any(not (540<=t<=810) for t,v in out):stop("out-of-session minute")
 return out
dates=[x[0] for x in c.execute("SELECT day FROM f10_day GROUP BY day HAVING COUNT(*)>=1400 ORDER BY day")]
if len(dates)!=11:stop("expected 11 candidate broad-coverage days; found "+repr(dates))
print("DAY | STOCK_DAYS | MEDIAN_POINTS | MIN_POINTS | P10_POINTS | MEDIAN_FIRST | MEDIAN_LAST | FIRST_AFTER_0910 | LAST_BEFORE_1300 | EXACT_DUPLICATES")
for day in dates:
 n=[];first=[];last=[];seen=set();dup=0
 for s,raw in c.execute("SELECT symbol,pts_json FROM f10_day WHERE day=?",(day,)):
  if s in seen:dup+=1
  seen.add(s)
  pts=parse(raw);n.append(len(pts));first.append(pts[0][0]);last.append(pts[-1][0])
 if dup:stop("duplicate identities "+day)
 def hh(t):return f"{int(t)//60:02d}:{int(t)%60:02d}"
 print(day,len(n),statistics.median(n),min(n),sorted(n)[int((len(n)-1)*.1)],hh(statistics.median(first)),hh(statistics.median(last)),sum(t>550 for t in first),sum(t<780 for t in last),dup)
print("AUDIT COMPLETED; row count alone does not establish complete minute coverage or market universe.")
