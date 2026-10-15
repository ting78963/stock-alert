#!/usr/bin/env python3
"""Read-only dynamic volume gate curve replay; exploratory cohort, no production writes."""
import csv,sqlite3,json,datetime as dt,statistics,collections,math
from pathlib import Path
P=Path("/tmp/a_b_handoff_xy_v1/points.csv")
D=Path("/var/data/stock-alert/backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3")
OUT=Path("/tmp/a_dynamic_curve_v1")
def fail(x): raise SystemExit("STOP / FAIL CLOSED: "+str(x))
if not P.exists() or not D.exists(): fail("missing points.csv or F10 database")
rows=list(csv.DictReader(P.open(encoding="utf-8-sig")))
if len(rows)!=182 or len({(r["date"],r["stock_id"]) for r in rows})!=182: fail("182 unique identities required")
con=sqlite3.connect("file:"+str(D)+"?mode=ro",uri=True)
if not {"symbol","day","pts_json"}.issubset({r[1] for r in con.execute("PRAGMA table_info(f10_day)")}): fail("unexpected F10 schema")
def tm(v):
 s=str(v).replace("T"," ").split()[-1][:5]
 try:
  t=dt.datetime.strptime(s,"%H:%M");return t.hour*60+t.minute
 except: fail("unparseable time "+str(v))
def pts_parse(raw):
 a=json.loads(raw)
 if not isinstance(a,list) or not a: fail("empty F10")
 out=[]
 for p in a:
  if isinstance(p,(list,tuple)) and len(p)>=2: t,v=p[:2]
  elif isinstance(p,dict):
   t=next((p[k] for k in ("minute","time","t","timestamp") if k in p),None)
   v=next((p[k] for k in ("cumulative_volume_zhang","cum","volume","v") if k in p),None)
  else: fail("bad F10 point")
  if t is None or v is None: fail("missing F10 fields")
  out.append((tm(t),float(v)))
 if any(out[i][0]>=out[i+1][0] or out[i][1]>out[i+1][1]+1e-8 for i in range(len(out)-1)): fail("noncausal or decreasing F10")
 return out
START=9*60; END=13*60+30
# Illustrative, NOT fitted or production recommendations. Threshold at 09:00=2000, 13:30=800.
def gate(t,shape):
 x=max(0,min(1,(t-START)/(END-START)))
 f={"linear":x,"early":1-(1-x)**2,"late":x*x}[shape]
 return 2000-1200*f
shapes=("linear","early","late")
detail=[]; missing=[]
for r in rows:
 day,s=r["date"],r["stock_id"]
 q=con.execute("SELECT pts_json FROM f10_day WHERE symbol=? AND day=?",(s,day)).fetchall()
 if len(q)!=1: missing.append((day,s));continue
 pts=pts_parse(q[0][0]);handoff=tm(r["discovered_at"])
 prior=[(t,v) for t,v in pts if t<handoff]
 if not prior: fail("no completed minute "+day+" "+s)
 observed=float(r["cumulative_volume_zhang"])
 if abs(prior[-1][1]-observed)>.05: fail("handoff volume mismatch "+day+" "+s)
 rec={"date":day,"stock_id":s,"handoff":r["discovered_at"],"handoff_volume":observed}
 for shape in shapes:
  # F10 time represents completed minute; candidate evaluation at next minute.
  hits=[(t,v) for t,v in pts if START<=t<END and t<handoff and v>=gate(t+1,shape)]
  t,v=hits[0] if hits else (None,None)
  rec[shape+"_cross"]=f"{t//60:02d}:{t%60:02d}" if t is not None else ""
  rec[shape+"_volume"]=round(v,2) if t is not None else ""
  rec[shape+"_lead_min"]=handoff-(t+1) if t is not None else ""
 detail.append(rec)
if missing: fail("missing F10 identities: "+repr(missing[:10]))
OUT.mkdir(exist_ok=True)
with (OUT/"detail.csv").open("w",newline="",encoding="utf-8") as f:
 w=csv.DictWriter(f,fieldnames=list(detail[0]));w.writeheader();w.writerows(detail)
print("AUDIT PASS 182 unique B-event stock-days; F10 match and handoff volume match 182/182")
print("NOTE: only intersections strictly BEFORE actual handoff are counted; no hindsight minutes.")
print("NOTE: candidate trigger is completed-minute observation +1 minute; not proof B could recognize then.")
print("CURVE | INTERSECT_BEFORE_HANDOFF | MEDIAN_LEAD_MIN | LEAD_GE_30 | LEAD_GE_60")
for shape in shapes:
 v=[r[shape+"_lead_min"] for r in detail if r[shape+"_lead_min"]!=""]
 print(shape,len(v),round(statistics.median(v),1) if v else "-",sum(x>=30 for x in v),sum(x>=60 for x in v))
print("EXAMPLES | greatest lead under linear")
for r in sorted((x for x in detail if x["linear_lead_min"]!=""),key=lambda x:x["linear_lead_min"],reverse=True)[:15]:
 print(r["date"],r["stock_id"],"cross",r["linear_cross"],"volume",r["linear_volume"],"handoff",r["handoff"],"lead_min",r["linear_lead_min"])
print("OUTPUT",OUT/"detail.csv")
print("LIMIT: selected B-event cohort only; no false-positive/API load estimate; threshold shapes are examples, not optimized.")
