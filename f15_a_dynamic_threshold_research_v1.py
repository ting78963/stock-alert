#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F15 signal-cohort minute replay, read-only. No API/LINE/production writes.
WARNING: volume+price proxy only; missing historical metadata, MA20, VCP,
FIFO and WAIT_DATA prohibit production threshold decisions.
"""
import argparse,csv,json,sqlite3,statistics,sys
from pathlib import Path
from collections import defaultdict
P=Path("/var/data/stock-alert")
def mm(s):
 h,m=map(int,str(s)[:5].split(":"));return h*60+m
def die(s):raise RuntimeError("STOP: "+s)
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--root",type=Path,default=P/"f15_eod"/"trajectory_v1")
 ap.add_argument("--f10",type=Path,default=P/"f10_baseline_v1.sqlite3")
 ap.add_argument("--output",type=Path,default=Path("/tmp/f15_a_dynamic_threshold_research_v1"))
 a=ap.parse_args()
 if not a.root.is_dir() or not a.f10.is_file():die("F15 or F10 source missing")
 if str(a.output.resolve()).startswith(str(P.resolve())):die("output cannot be in production data")
 records=defaultdict(list)
 for p in sorted(a.root.glob("*/*.json")):
  if p.name=="manifest.json":continue
  x=json.loads(p.read_text(encoding="utf-8"));i=x["identity"]
  if x.get("schema")!="f15_trajectory_v1" or p.parent.name!=i["date"]:die("identity/schema mismatch "+str(p))
  rows=x["trajectory_raw_1m"];prior=-1;cum=0.
  for b in rows:
   t=mm(b["minute"]);v=float(b["volume"]);q=float(b["cum_volume"])
   if t<=prior or v<0 or abs(q-cum-v)>max(.01,q*1e-7):die("invalid 1m trajectory "+str(p))
   prior=t;cum=q
  records[(i["date"],str(i["stock_id"]).zfill(4))].append(x)
 if not records:die("no signal files")
 db=sqlite3.connect("file:"+str(a.f10)+"?mode=ro",uri=True)
 rules={"PROD_4000_2000":(4000,2000,2000)}
 for e in (800,1000,1500,2000,3000,4000):
  for m in (800,1000,1500,2000,3000):
   for l in (800,1000,1500,2000):rules[f"E{e}_M{m}_L{l}"]=(e,m,l)
 details=[];missing=[];valid=0
 for (day,sid),xs in records.items():
  x=xs[0];bar=x["trajectory_raw_1m"];ident=x["identity"];anchor=x["causal_anchor"]
  labels=[f'{z["identity"]["signal_class"]}@{z["identity"]["recognition_time"]}' for z in xs]
  recognition=min(mm(z["identity"]["recognition_time"]) for z in xs)
  hist=db.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(sid,day)).fetchall()
  if len(hist)<5:
   missing.append((day,sid,len(hist),"LESS_THAN_5_PREVIOUS_SESSIONS"));continue
  hist=list(reversed(hist));days=[]
  for ds,full,raw in hist:
   pts=json.loads(raw)
   if ds>=day or float(full)<=0 or not pts:die("bad F10 "+sid+" "+ds)
   days.append((float(full),[(str(t)[:5],float(v)) for t,v in pts]))
  avg5=sum(z[0] for z in days[-5:])/5;prev=days[-1][0]
  if avg5<=0 or prev<=0:die("bad F10 baseline "+sid)
  curve=[]
  for b in bar:
   t=mm(b["minute"]);vol=float(b["cum_volume"]);f=[]
   for full,pts in days:
    cum=0.
    for ts,q in pts:
     if mm(ts)<=t:cum=q
     else:break
    f.append(cum/full)
   f10=sum(f)/len(f)
   if f10<=0:continue
   projected=vol/f10;vr=projected/avg5;evg=(projected/prev-1)*100
   curve.append((t,vol,vr>=1.5 or evg>=50,float(b["close_gain_pct"])))
  if not curve:
   missing.append((day,sid,len(hist),"NO_VALID_F10_CUTOFF"));continue
  valid+=1
  for name,sched in rules.items():
   arm=False;firstvol=None;firstarm=None;firstproxy=None
   for t,vol,anomaly,gain in curve:
    if t<541:continue
    threshold=sched[0] if t<550 else sched[1] if t<600 else sched[2]
    if vol<threshold:continue
    if firstvol is None:firstvol=t
    if anomaly and not arm:arm=True;firstarm=t
    if arm and gain>=3 and firstproxy is None:firstproxy=t
   fmt=lambda z: "" if z is None else f"{z//60:02}:{z%60:02}"
   details.append(dict(rule=name,date=day,stock_id=sid,stock_name=ident.get("stock_name",""),signals=";".join(labels),recognition=fmt(recognition),discovered_at=anchor.get("discovered_at"),first_volume=fmt(firstvol),first_arm=fmt(firstarm),first_proxy=fmt(firstproxy),lead_minutes=recognition-firstproxy if firstproxy is not None else "",before_signal=int(firstproxy is not None and firstproxy<=recognition)))
 db.close()
 if not details:die("no usable F10 coverage")
 a.output.mkdir(parents=True,exist_ok=True)
 def write(fn,rows):
  if not rows:return
  with (a.output/fn).open("w",encoding="utf-8-sig",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 write("per_stock_all_rules.csv",details)
 write("excluded_missing_f10.csv",[dict(date=d,stock_id=s,available_days=n,reason=r) for d,s,n,r in missing])
 summary=[]
 for name,sched in rules.items():
  ds=[z for z in details if z["rule"]==name];hits=[z for z in ds if z["before_signal"]]
  summary.append(dict(rule=name,early=sched[0],mid=sched[1],late=sched[2],eligible=len(ds),before_signal=len(hits),coverage_pct=round(100*len(hits)/len(ds),2),median_lead=statistics.median(z["lead_minutes"] for z in hits) if hits else ""))
 write("schedule_comparison.csv",summary)
 audit=dict(signal_files=sum(map(len,records.values())),unique_stock_days=len(records),f10_eligible=valid,f10_missing=len(missing),research_only=True,not_reconstructed=["MA20","metadata","industry","VCP","FIFO","WAIT_DATA","5-second snapshot","API load"],decision="DO_NOT_DEPLOY_THRESHOLD")
 (a.output/"audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
 print("[AUDIT]",json.dumps(audit,ensure_ascii=False))
 print("[OUTPUT]",a.output)
 for row in sorted(summary,key=lambda z:-z["before_signal"])[:10]:print("[COMPARE]",row)
if __name__=="__main__":
 try:main()
 except Exception as e:print(str(e),file=sys.stderr);sys.exit(2)
