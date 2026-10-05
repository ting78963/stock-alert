# -*- coding: utf-8 -*-
"""F15 Trajectory Store v1.
Research archive only. Never changes A/B/P1 recognition or LINE semantics.
Builds one immutable-style research record per delivered signal from persisted
production events + Fugle 1m bars. Raw trajectory is kept separately from
post-T0 outcomes so future features can be recomputed without losing source data.
"""
from __future__ import annotations
import json,math,runpy,time
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import f15_eod_signal_report as f15
TPE=ZoneInfo("Asia/Taipei");OUT=f15.OUT/"trajectory_v1";SCHEMA="f15_trajectory_v1"

def atomic(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+".tmp");q.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8");q.replace(p)
def nt(s):return f15.normt(s)
def minute_index(s):
 h,m=map(int,nt(s).split(":"));return h*60+m
def safe(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except:return None
def first_hit(rows,t0,pct):
 for r in rows:
  if minute_index(r["minute"])>=minute_index(t0) and r["high_gain_pct"]>=pct:return r["minute"]
 return None
def event_meta(e):
 # Preserve every production-event fact verbatim as a separate source snapshot.
 # This intentionally captures future A/B timing fields without inventing semantics.
 return {k:v for k,v in e.items()}
def build_one(day,e,M,key):
 sid=str(e["stock_id"]).zfill(4);cls=str(e["signal_class"]).upper();t0=nt(e["recognition_time"])
 bars=M["adapt"](M["fetch"](key,sid,day),day,sid);_,prev,pvol=M["fetch_prev"](key,sid,day)
 if not bars:raise RuntimeError(f"F15 trajectory empty bars {day} {sid}")
 raw=[];cum=0.0;run_hi=-float("inf")
 for b in bars:
  o,h,l,c,v=map(float,(b["open"],b["high"],b["low"],b["close"],b["volume"]));cum+=max(v,0);run_hi=max(run_hi,h)
  raw.append({"minute":nt(b["minute"]),"open":o,"high":h,"low":l,"close":c,"volume":v,"cum_volume":cum,"open_gain_pct":(o/prev-1)*100,"high_gain_pct":(h/prev-1)*100,"low_gain_pct":(l/prev-1)*100,"close_gain_pct":(c/prev-1)*100,"drawdown_from_running_high_pct":(c/run_hi-1)*100 if run_hi>0 else None,"raw_vr_prev_day":cum/pvol if pvol>0 else None})
 by={r["minute"]:r for r in raw}
 if t0 not in by and e.get("frozen_early_price") is None:raise RuntimeError(f"F15 trajectory missing T0 {day} {sid} {t0}")
 t0_price=float(by[t0]["close"]) if t0 in by else float(e["frozen_early_price"]);post=[r for r in raw if minute_index(r["minute"])>=minute_index(t0)]
 if not post:raise RuntimeError(f"F15 trajectory no post-T0 rows {day} {sid}")
 mfe=max((r["high"]/t0_price-1)*100 for r in post);mae=min((r["low"]/t0_price-1)*100 for r in post);peak=max(post,key=lambda r:r["high"]);close=raw[-1]["close"]
 horizons={}
 for n in (5,10,20,30,60):
  z=[r for r in post if minute_index(r["minute"])<=minute_index(t0)+n]
  horizons[str(n)]={"mfe_pct":max(((r["high"]/t0_price-1)*100 for r in z),default=None),"mae_pct":min(((r["low"]/t0_price-1)*100 for r in z),default=None),"last_close_return_pct":((z[-1]["close"]/t0_price-1)*100 if z else None)}
 rec={"schema":SCHEMA,"identity":{"date":day,"stock_id":sid,"stock_name":str(e.get("stock_name") or sid),"signal_class":cls,"recognition_time":t0},"causal_anchor":{"prior_close":prev,"prior_day_volume_1m_sum":pvol,"recognition_price":t0_price,"recognition_gain_pct":(t0_price/prev-1)*100,"discovered_at":e.get("discovered_at"),"late_discovery":bool(e.get("late_discovery")),"delay_seconds":max(0,f15.secs(e["discovered_at"])-f15.secs(t0)) if e.get("late_discovery") else 0},"production_event_snapshot":event_meta(e),"trajectory_raw_1m":raw,"outcome_post_t0":{"close_price":close,"close_return_from_t0_pct":(close/t0_price-1)*100,"close_gain_vs_prior_pct":(close/prev-1)*100,"mfe_d0_from_t0_pct":mfe,"mae_d0_from_t0_pct":mae,"peak_minute":peak["minute"],"peak_gain_vs_prior_pct":peak["high_gain_pct"],"first_hit_vs_prior":{"3pct":first_hit(raw,t0,3.0),"5pct":first_hit(raw,t0,5.0),"7pct":first_hit(raw,t0,7.0),"9_5pct":first_hit(raw,t0,9.5)},"horizons_from_t0_minutes":horizons},"feature_policy":{"raw_first":True,"outcome_blind_boundary":"Only identity/causal_anchor + trajectory rows <= recognition_time may be used for T0 quality prediction. outcome_post_t0 is label-only.","derived_features_version":"none_v1"},"built_at_taipei":datetime.now(TPE).isoformat(timespec="seconds")}
 return rec

def build_day(day):
 events=f15.load_events(day)
 if not events:return {"day":day,"status":"no_events","written":0,"skipped":0}
 M=runpy.run_path(str(f15.ENGINE),run_name="__f15_trajectory_engine__");key,_=M["find_key"]();written=skipped=0;manifest=[]
 for e in events:
  sid=str(e["stock_id"]).zfill(4);cls=str(e["signal_class"]).upper();t0=nt(e["recognition_time"]);p=OUT/day/f"{sid}_{cls}_{t0.replace(':','')}.json"
  if p.exists():
   old=json.loads(p.read_text(encoding="utf-8"));ident=old.get("identity",{})
   if old.get("schema")!=SCHEMA or ident.get("date")!=day or ident.get("stock_id")!=sid or ident.get("signal_class")!=cls or ident.get("recognition_time")!=t0:raise RuntimeError(f"F15 trajectory identity conflict {p}")
   skipped+=1
  else:atomic(p,build_one(day,e,M,key));written+=1
  manifest.append(p.name)
 atomic(OUT/day/"manifest.json",{"schema":SCHEMA,"date":day,"files":sorted(manifest),"count":len(manifest),"updated_at_taipei":datetime.now(TPE).isoformat(timespec="seconds")})
 print(f"[F15 TRAJECTORY] {day} signals={len(events)} written={written} skipped={skipped}",flush=True);return {"day":day,"status":"ok","written":written,"skipped":skipped}
def days(n=8):
 d=datetime.now(TPE).date();return [(d-timedelta(days=i)).isoformat() for i in range(n-1,-1,-1)]
def loop():
 OUT.mkdir(parents=True,exist_ok=True)
 while True:
  now=datetime.now(TPE)
  # Research archive is post-close only: zero intraday competition with A/B.
  if (now.hour,now.minute)>=(13,45):
   for day in days():
    try:build_day(day)
    except BaseException as ex:print(f"[F15 TRAJECTORY FAIL] {day} {type(ex).__name__}: {ex}",flush=True)
  time.sleep(900)
