#!/usr/bin/env python3
"""Read-only AND-gate replay of completed F15 checkpoint identities. No network."""
import datetime, importlib.util, json, math, sqlite3, statistics, sys
from pathlib import Path
P=Path("/var/data/stock-alert")
O=P/"_research_output/f15_174_api_800_1000_v1"
def stop(s):raise SystemExit("AUDIT STOP: "+s)
def m(s):
 h,mi=map(int,str(s)[:5].split(":"));return h*60+mi
def main():
 ck=O/"progress_174.json"
 if not ck.exists():stop("missing checkpoint")
 rows=json.loads(ck.read_text())
 if len(rows)!=24:stop(f"expected 24 completed, got {len(rows)}")
 spec=importlib.util.spec_from_file_location("a_and_readonly",Path.cwd()/"fugle_a_scanner_v2_4.py")
 a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
 f10=sqlite3.connect("file:"+str(P/"f10_baseline_v1.sqlite3")+"?mode=ro",uri=True)
 hist=sqlite3.connect("file:"+str(P/"shared_history_stage_v1.sqlite3")+"?mode=ro",uri=True)
 cal=[r[0] for r in hist.execute("SELECT day FROM daily_ohlcv GROUP BY day HAVING COUNT(*)>=1000 ORDER BY day")]
 summary=[]
 try:
  for r in rows:
   d,s,c,rt=r["date"],r["stock_id"],r["class"],r["recognition"]
   files=list((P/"f15_eod/trajectory_v1"/d).glob("*.json"))
   matches=[]
   for f in files:
    if f.name=="manifest.json":continue
    obj=json.loads(f.read_text());i=obj["identity"]
    if (str(i["date"]),str(i["stock_id"]),str(i["signal_class"]),str(i["recognition_time"]))==(d,s,c,rt):matches.append(obj)
   if len(matches)!=1:stop(f"F15 identity not unique {d} {s} {c}")
   prev=[x for x in cal if x<d][-10:]
   if len(prev)!=10:stop(f"calendar {d}")
   existing={x[0]:(x[1],x[2]) for x in f10.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(s,d))}
   days=[]
   for ds in prev:
    if ds in existing:
     full,raw=existing[ds];pts=json.loads(raw)
    else:
     p=O/"api_day_cache"/f"{s}_{ds}.json"
     if not p.exists():stop(f"missing cached minute bars {s} {ds}")
     payload=json.loads(p.read_text())
     if str(payload.get("symbol"))!=s or str(payload.get("timeframe"))!="1":stop(f"cache identity {s} {ds}")
     pts=[];full=0.
     for x in payload["data"]:
      if str(x["date"])[:10]!=ds:stop(f"cache date {s} {ds}")
      full+=float(x.get("volume") or 0)
      pts.append((str(x["date"])[11:19],full))
    if not pts or float(full)<=0:stop(f"invalid history {s} {ds}")
    days.append({"date":ds,"full":float(full),"pts":pts})
   ad=a.FugleAdapter.__new__(a.FugleAdapter)
   key=f"estvr5|{s}|{d}"
   ad.history_cache={key:days};ad._estvr5_cache={key:days};ad._estvr5_curve_cache={}
   first={800:None,1000:None}
   for ob in matches[0]["trajectory_raw_1m"]:
    t=m(ob["minute"])
    if t>=m(rt):continue
    v=float(ob["cum_volume"])
    if not math.isfinite(v) or v<0:stop(f"volume {s}")
    dt=datetime.datetime.fromisoformat(f"{d}T{t//60:02d}:{t%60:02d}:00")
    frac,avg5,prev1,n=ad.estimated_vr5_parts(s,d,dt)
    projected=v/frac
    evg5=projected/avg5
    evg1=projected/prev1
    if evg5>=2.5 and evg1>=2.5:
     for th in first:
      if first[th] is None and v>=th:first[th]=t
   # AND is subset of OR; any violation means wrong units/semantics.
   for th in first:
    if first[th] is not None and r.get(f"first_{th}") is None:stop(f"AND not subset OR {s} {th}")
   summary.append((d,s,c,rt,first[800],first[1000]))
   print(f"CHECKED {len(summary)}/24 {d} {s} {c}",flush=True)
  for th,ix in ((800,4),(1000,5)):
   hit=[z for z in summary if z[ix] is not None]
   abc=[z for z in hit if z[2]!="P1"]
   p1=[z for z in hit if z[2]=="P1"]
   print(f"AND_{th}: total={len(hit)}/24 ABC={len(abc)}/7 P1={len(p1)}/17 no_early={24-len(hit)}")
   for z in hit:print(f"  {z[0]} {z[1]} {z[2]} first={z[ix]//60:02d}:{z[ix]%60:02d} lead={m(z[3])-z[ix]}min")
  print("READ ONLY; NO API; signal-only sample, not all-market B load.")
 finally:f10.close();hist.close()
if __name__=="__main__":main()
