#!/usr/bin/env python3
"""174 F15-only Fugle API replay: compare 800 vs 1000. No production writes."""
import argparse, collections, datetime, importlib.util, json, math, os, sqlite3, statistics, sys, time, urllib.parse
from pathlib import Path

P=Path("/var/data/stock-alert"); ROOT=P/"f15_eod/trajectory_v1"
OUT=P/"_research_output"/"f15_174_api_800_1000_v1"
def stop(x): raise SystemExit("AUDIT STOP: "+str(x))
def minute(s):
 try:
  h,m=map(int,str(s)[:5].split(":")); assert 9<=h<=13 and 0<=m<60
  return h*60+m
 except Exception: stop("invalid minute "+str(s))
def valid(v):
 x=float(v)
 if not math.isfinite(x) or x<0:stop("invalid volume")
 return x
def read_db(path):
 if not path.is_file():stop("missing "+str(path))
 return sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True)
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--max-requests",type=int,default=1000)
 ap.add_argument("--sleep",type=float,default=1.1)
 args=ap.parse_args()
 if args.max_requests<1 or args.sleep<0.5:stop("unsafe API budget/rate")
 src=Path.cwd()/"fugle_a_scanner_v2_4.py"
 if not src.is_file():stop("formal A source missing at "+str(src))
 spec=importlib.util.spec_from_file_location("a_replay_readonly",src)
 a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
 fs=sorted(x for x in ROOT.glob("20??-??-??/*.json") if x.name!="manifest.json")
 if len(fs)!=184:stop("F15 identity count not 184: "+str(len(fs)))
 f10=read_db(P/"f10_baseline_v1.sqlite3")
 hist=read_db(P/"shared_history_stage_v1.sqlite3")
 try:
  cal=[r[0] for r in hist.execute("SELECT day FROM daily_ohlcv GROUP BY day HAVING COUNT(*)>=1000 ORDER BY day")]
  identities=[];seen=set()
  for f in fs:
   x=json.loads(f.read_text());i=x["identity"];d=str(i["date"]);s=str(i["stock_id"]);c=str(i["signal_class"]);rt=str(i["recognition_time"])
   ident=(d,s,c,rt)
   if d!=f.parent.name or c not in ("A","B","C","P1") or ident in seen:stop("F15 identity "+str(f))
   seen.add(ident)
   obs=[];lastt=-1;lastv=-1
   for row in x["trajectory_raw_1m"]:
    t=minute(row["minute"]);v=valid(row["cum_volume"])
    if t<=lastt or v<lastv:stop("nonmonotonic F15 "+str(f))
    lastt=t;lastv=v
    if t<minute(rt):obs.append((t,v))
   if not obs:stop("no pre-recognition F15 "+str(f))
   rows=f10.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(s,d)).fetchall()
   if len(rows)<10:identities.append((ident,obs))
  if len(identities)!=174:stop("not exactly 174 missing F10 identities: "+str(len(identities)))
  print("IDENTITY PASS: 184 total, 174 API reconstruction, 10 excluded",flush=True)
  key=a.fugle_key()
  OUT.mkdir(parents=True,exist_ok=True)
  cache=OUT/"api_day_cache";cache.mkdir(exist_ok=True)
  requests=0;results=[]
  checkpoint=OUT/"progress_174_and_v3.json"
  if checkpoint.exists():
   old=json.loads(checkpoint.read_text())
   if not isinstance(old,list):stop("checkpoint not a list")
   expected=[x[0] for x in identities]
   for j,row in enumerate(old):
    if j>=len(expected) or (row["date"],row["stock_id"],row["class"],row["recognition"])!=expected[j]:stop("checkpoint identity mismatch "+str(j))
   results=old
  print("RESUME_COMPLETED",len(results),"OF",len(identities),flush=True)
  v2file=OUT/"results_174_skip404_v2.json"
  if not v2file.exists():stop("missing completed v2 result")
  v2rows=json.loads(v2file.read_text())
  if len(v2rows)!=174:stop("v2 result not 174")
  for idx,((d,s,c,rt),obs) in enumerate(identities,1):
   if idx<=len(results):continue
   print(f"START {idx}/{len(identities)} {d} {s} {c}",flush=True)
   old=v2rows[idx-1]
   if (old["date"],old["stock_id"],old["class"],old["recognition"])!=(d,s,c,rt):stop("v2 identity mismatch "+str(idx))
   if old.get("status")=="MISSING_HISTORY":
    results.append(dict(old))
    tmp=checkpoint.with_suffix(".json.tmp");tmp.write_text(json.dumps(results,ensure_ascii=False,indent=2));tmp.replace(checkpoint)
    print(f"SKIP {idx}/174 known missing history",flush=True)
    continue
   prev=[x for x in cal if x<d][-10:]
   if len(prev)!=10:stop("calendar <10 "+s+" "+d)
   rows=f10.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(s,d)).fetchall()
   available={z[0]:(z[1],z[2]) for z in rows}
   days=[];missing_reason=None
   for ds in prev:
    if ds in available:
     full,raw=available[ds];pts=json.loads(raw)
     days.append({"date":ds,"full":valid(full),"pts":pts})
     continue
    file=cache/(s+"_"+ds+".json")
    if file.exists():
     payload=json.loads(file.read_text())
    else:
     stop(f"NO NETWORK: cache missing {s} {ds}")
     q=urllib.parse.urlencode({"timeframe":"1","from":ds,"to":ds,"fields":"open,high,low,close,volume,average","sort":"asc"})
     url=f"{a.BASE}/historical/candles/{urllib.parse.quote(s)}?{q}"
     try:payload=a.http_json(url,key)
     except Exception as e:
      if "HTTP 404" in str(e):
       missing_reason=f"Fugle HTTP 404 {s} {ds}"
       requests+=1;time.sleep(args.sleep)
       break
      stop(f"API failed {s} {ds}: {e}; rerun resumes saved cache")
     if str(payload.get("symbol") or "")!=s or str(payload.get("timeframe") or "")!="1":stop("API identity "+s+" "+ds)
     if not isinstance(payload.get("data"),list) or not payload["data"]:stop("API empty "+s+" "+ds)
     # Save only after validating identity; no credentials in response.
     file.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
     requests+=1;time.sleep(args.sleep)
    full=0.;pts=[];seen_t=set()
    for r in payload["data"]:
     stamp=str(r.get("date") or "")
     if stamp[:10]!=ds or len(stamp)<16:stop("API date leakage "+s+" "+ds)
     tm=stamp[11:19]
     if tm in seen_t:stop("API duplicate minute "+s+" "+ds)
     seen_t.add(tm);full+=valid(r.get("volume") or 0);pts.append((tm,full))
    if full<=0:stop("API zero volume "+s+" "+ds)
    days.append({"date":ds,"full":full,"pts":pts})
   if missing_reason is not None:
    results.append({"date":d,"stock_id":s,"class":c,"recognition":rt,
      "status":"MISSING_HISTORY","reason":missing_reason,
      "first_800":None,"first_1000":None,"lead_800":None,"lead_1000":None})
    tmp=checkpoint.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(results,ensure_ascii=False,indent=2))
    tmp.replace(checkpoint)
    print(f"SKIP {idx}/{len(identities)} {missing_reason}",flush=True)
    continue
   # Invoke formal A's ORIGINAL estimated_vr5_parts method with isolated RAM cache.
   adapter=a.FugleAdapter.__new__(a.FugleAdapter)
   ck=f"estvr5|{s}|{d}"
   adapter.history_cache={ck:days};adapter._estvr5_cache={ck:days};adapter._estvr5_curve_cache={}
   first={800:None,1000:None}
   for t,v in obs:
    dt=datetime.datetime.fromisoformat(d+"T"+f"{t//60:02d}:{t%60:02d}:00")
    f10_fraction,avg5,prev1,n=adapter.estimated_vr5_parts(s,d,dt)
    projected=v/f10_fraction
    # Research gate from previous comparison: EstVR5>=2.5 OR EVG>=150%.
    if projected/avg5<2.5 or projected/prev1<2.5:continue
    for threshold in first:
     if first[threshold] is None and v>=threshold:first[threshold]=t
   rec=minute(rt)
   results.append({"date":d,"stock_id":s,"class":c,"recognition":rt,"status":"COMPLETE",
      "first_800":first[800],"first_1000":first[1000],
      "lead_800":rec-first[800] if first[800] is not None else None,
      "lead_1000":rec-first[1000] if first[1000] is not None else None})
   tmp=checkpoint.with_suffix(".json.tmp")
   tmp.write_text(json.dumps(results,ensure_ascii=False,indent=2))
   tmp.replace(checkpoint)
   print(f"COMPLETED {idx}/{len(identities)} {d} {s} {c}",flush=True)
   if idx%10==0 or idx==len(identities):print(f"PROGRESS {idx}/{len(identities)} API_REQUESTS_THIS_RUN={requests}",flush=True)
  path=OUT/"results_174_and_v3.json";path.write_text(json.dumps(results,ensure_ascii=False,indent=2))
  print("STRICT AND: volume threshold AND EVG5>=2.5 AND EVG1>=2.5")
  print("COMPLETE",sum(r.get("status")!="MISSING_HISTORY" for r in results),"MISSING_HISTORY",sum(r.get("status")=="MISSING_HISTORY" for r in results))
  for th in (800,1000):
   for group in ("ABC","P1"):
    vals=[r["lead_"+str(th)] for r in results if (r["class"]!="P1")==(group=="ABC") and r["lead_"+str(th)] is not None]
    print(th,group,"early",len(vals),"median_lead",statistics.median(vals) if vals else "N/A")
  better=[r for r in results if r["lead_800"] is not None and r["lead_1000"] is not None]
  diffs=[r["lead_800"]-r["lead_1000"] for r in better]
  print("BOTH_TRIGGERED",len(better),"800_EXTRA_LEAD_MEDIAN",statistics.median(diffs) if diffs else "N/A")
  print("RESULT",path)
  print("NO NETWORK; historical cache only.")
  print("LIMIT: MISSING_HISTORY rows are excluded from trigger counts, NOT negatives.")
  print("LIMIT: F15 signal-only sample; cannot infer all-market B load/false positives.")
  print("LIMIT: Historical API backfill is retrospective, not proof data were available at the time.")
 finally:f10.close();hist.close()
if __name__=="__main__":main()
