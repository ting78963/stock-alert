#!/usr/bin/env python3
"""F15 D5 volume-only replay. Read-only input; writes /tmp only. No API, LINE or production changes."""
import csv,json,math,statistics
from pathlib import Path
from collections import Counter
ROOT=Path("/var/data/stock-alert/f15_eod/trajectory_v1")
OUT=Path("/tmp/f15_d5_replay_20261017")
RULES={"OLD":[(541,4000),(550,2000)],"D5":[(541,4000),(550,1700),(560,1400),(570,1100),(580,1000)],"FIX1000":[(541,1000)],"FIX1500":[(541,1500)],"FIX2000":[(541,2000)]}
def stop(s):raise SystemExit("AUDIT STOP: "+s)
def tm(s):
 try:
  h,m=map(int,str(s)[:5].split(":"));v=h*60+m
  if not 540<=v<=810 or not 0<=m<60:raise ValueError()
  return v
 except Exception:stop("bad time "+repr(s))
def fmt(t):return "" if t is None else f"{t//60:02d}:{t%60:02d}"
def hit(bars,rule,end):
 for t,c in bars:
  if t<541 or t>end:continue
  th=next((n for start,n in reversed(rule) if t>=start),None)
  if th is not None and c>=th:return t
 return None
def write(name,rows):
 with (OUT/name).open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
if not ROOT.is_dir():stop("missing F15 trajectory root")
days=sorted(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith("20"))
if not days:stop("no F15 day")
rows=[];seen=set();audit=[];excluded=0
for day in days:
 mf=day/"manifest.json"
 if not mf.is_file():stop("manifest missing "+day.name)
 try:json.loads(mf.read_text(encoding="utf-8"))
 except Exception:stop("manifest invalid "+day.name)
 files=sorted(p for p in day.glob("*.json") if p.name!="manifest.json")
 if not files:stop("empty day "+day.name)
 for p in files:
  try:x=json.loads(p.read_text(encoding="utf-8"))
  except Exception:stop("invalid JSON "+str(p))
  ident=x.get("identity",{});sid=str(ident.get("stock_id",""))
  if sid=="4906":excluded+=1;continue
  cls=str(ident.get("signal_class",""));rec=tm(ident.get("recognition_time"))
  if ident.get("date")!=day.name or not sid or not cls:stop("identity mismatch "+str(p))
  key=(day.name,sid,cls,rec)
  if key in seen:stop("duplicate identity "+str(key))
  seen.add(key)
  raw=x.get("trajectory_raw_1m")
  if not isinstance(raw,list) or not raw:stop("missing bars "+str(key))
  bars=[];cum=0;last=-1
  for b in raw:
   t=tm(b.get("minute"))
   try:v=float(b.get("volume"));reported=float(b.get("cum_volume"))
   except Exception:stop("invalid volume "+str(key))
   if not all(map(math.isfinite,(v,reported))) or v<0 or t<=last:stop("bad minute ordering/volume "+str(key))
   cum+=v
   if abs(cum-reported)>max(.1,cum*.0001):stop("cumulative mismatch "+str(key))
   bars.append((t,cum));last=t
  if bars[0][0]>541 or bars[-1][0]<rec:stop("insufficient minute coverage "+str(key))
  discovered=x.get("causal_anchor",{}).get("discovered_at")
  if not discovered:stop("missing discovered_at "+str(key))
  disc=tm(discovered)
  h={name:hit(bars,rule,rec) for name,rule in RULES.items()}
  if h["OLD"] is not None and (h["D5"] is None or h["D5"]>h["OLD"]):stop("D5 monotonicity violation "+str(key))
  delta=h["OLD"]-h["D5"] if h["OLD"] is not None and h["D5"] is not None else None
  if h["D5"] is None:category="NO_D5"
  elif h["OLD"] is None:category="D5_ONLY_BEFORE_B"
  elif delta>=30:category="EARLY_30_PLUS"
  elif delta>0:category="EARLY_1_TO_29"
  else:category="SAME"
  rows.append(dict(date=day.name,stock_id=sid,stock_name=ident.get("stock_name",""),signal_class=cls,recognition_time=fmt(rec),discovered_at=fmt(disc),old_hit=fmt(h["OLD"]),d5_hit=fmt(h["D5"]),fixed1000_hit=fmt(h["FIX1000"]),fixed1500_hit=fmt(h["FIX1500"]),fixed2000_hit=fmt(h["FIX2000"]),advance_minutes="" if delta is None else delta,category=category,d5_lead_vs_discovery="" if h["D5"] is None else disc-h["D5"],volume_only=1))
 audit.append(dict(date=day.name,files=len(files),manifest="PASS"))
if not rows:stop("no eligible signals")
counts=Counter(r["category"] for r in rows)
OUT.mkdir(parents=True,exist_ok=True)
write("signal_details.csv",rows);write("source_audit.csv",audit)
summary=[dict(category=k,count=counts[k]) for k in ["SAME","EARLY_1_TO_29","EARLY_30_PLUS","D5_ONLY_BEFORE_B","NO_D5"]]
write("summary.csv",summary)
print("AUDIT PASS | dates",len(days),"signals",len(rows),"excluded_4906",excluded)
for r in summary:print(r["category"],r["count"])
delta=[r["advance_minutes"] for r in rows if isinstance(r["advance_minutes"],int)]
print("PAIRED_MEDIAN_ADVANCE_MIN",statistics.median(delta) if delta else "NA")
print("RESULT",OUT)
print("LIMIT: volume-only until B recognition; NOT actual A handoff or all-market load")
