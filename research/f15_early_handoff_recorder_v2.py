#!/usr/bin/env python3
"""F15 research-only recorder V2: unknown source timestamp is explicit, not fabricated.
No production imports, API, LINE or production writes. CLI supports selftest only.
"""
import datetime as dt,json,os,tempfile,argparse,math
from pathlib import Path
from zoneinfo import ZoneInfo
TZ=ZoneInfo("Asia/Taipei")
SCHEMA="f15_early_handoff_candidate_v2"
THRESHOLDS={"volume_zhang":1000,"evg5":2.5,"evg1":2.5}
def require(ok,msg):
 if not ok:raise ValueError(msg)
def timestamp(value,label,date):
 require(isinstance(value,str),label+" missing")
 try:t=dt.datetime.fromisoformat(value)
 except (TypeError,ValueError):raise ValueError(label+" invalid")
 require(t.tzinfo is not None and t.utcoffset() is not None,label+" must be timezone aware")
 require(t.astimezone(TZ).date().isoformat()==date,label+" date mismatch")
 return t
def event(*,date,stock_id,observed_at,volume_zhang,evg5,evg1,
          f10_projected_zhang,prior5_avg_zhang,prior1_volume_zhang,
          source,source_version,source_data_time=None):
 require(isinstance(date,str) and dt.date.fromisoformat(date).isoformat()==date,"invalid date")
 require(isinstance(stock_id,str) and stock_id.isdigit() and len(stock_id) in (4,5,6),"invalid stock_id")
 obs=timestamp(observed_at,"observed_at",date)
 vals={"volume":volume_zhang,"evg5":evg5,"evg1":evg1,"projected":f10_projected_zhang,
       "prior5":prior5_avg_zhang,"prior1":prior1_volume_zhang}
 for k,v in vals.items():
  require(type(v) in (int,float) and math.isfinite(v) and 0<=v<1e12,k+" invalid")
 require(prior5_avg_zhang>0 and prior1_volume_zhang>0,"invalid denominator")
 require(isinstance(source,str) and bool(source) and isinstance(source_version,str) and bool(source_version),"missing provenance")
 require(abs(f10_projected_zhang/prior5_avg_zhang-evg5)<1e-7*max(1,evg5),"evg5 calculation mismatch")
 require(abs(f10_projected_zhang/prior1_volume_zhang-evg1)<1e-7*max(1,evg1),"evg1 calculation mismatch")
 if source_data_time is None:
  source_status="UNKNOWN"
 else:
  src=timestamp(source_data_time,"source_data_time",date)
  require(src<=obs,"source timestamp after observation")
  source_status="KNOWN"
 if not(volume_zhang>=1000 and evg5>=2.5 and evg1>=2.5):return None
 return {"schema":SCHEMA,"mode":"SHADOW_ONLY","date":date,"stock_id":stock_id,
         "first_shadow_observed_at":observed_at,"observed_at":observed_at,
         "observation_minute_proxy":obs.astimezone(TZ).strftime("%H:%M"),
         "market_first_eligible_minute":None,"market_first_eligible_certified":False,
         "source_data_time":source_data_time,"source_data_time_status":source_status,
         "cum_volume_zhang":volume_zhang,"evg5":evg5,"evg1":evg1,
         "f10_projected_zhang":f10_projected_zhang,"prior5_avg_zhang":prior5_avg_zhang,
         "prior1_volume_zhang":prior1_volume_zhang,"source":source,
         "source_version":source_version,"thresholds":dict(THRESHOLDS),
         "b_handoff_performed":False}
def append_once(root,record):
 require(isinstance(record,dict) and record.get("schema")==SCHEMA,"invalid record")
 date=record["date"];sym=record["stock_id"]
 require(dt.date.fromisoformat(date).isoformat()==date and sym.isdigit() and len(sym) in (4,5,6),"invalid identity")
 folder=Path(root)/"early_handoff_v2"/date
 folder.mkdir(parents=True,exist_ok=True)
 target=folder/(sym+".json")
 payload=(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
 try:
  with target.open("xb") as f:
   f.write(payload);f.flush();os.fsync(f.fileno())
  return "CREATED",target
 except FileExistsError:
  existing=json.loads(target.read_text(encoding="utf-8"))
  require(existing.get("schema")==SCHEMA and existing.get("date")==date and existing.get("stock_id")==sym,"identity conflict")
  return "ALREADY_EXISTS",target
def selftest():
 with tempfile.TemporaryDirectory(prefix="f15_v2_") as root:
  base=dict(date="2026-10-12",stock_id="1326",observed_at="2026-10-12T09:10:10+08:00",
    volume_zhang=1100,evg5=2.75,evg1=2.75,f10_projected_zhang=5500,
    prior5_avg_zhang=2000,prior1_volume_zhang=2000,
    source="SYNTHETIC_FIXTURE",source_version="v2")
  e=event(**base)
  assert e["source_data_time_status"]=="UNKNOWN" and e["market_first_eligible_minute"] is None
  assert e["observation_minute_proxy"]=="09:10"
  s,p=append_once(root,e);assert s=="CREATED"
  s,_=append_once(root,e);assert s=="ALREADY_EXISTS"
  assert json.loads(p.read_text())==e
  b=dict(base,source_data_time="2026-10-12T09:10:00+08:00")
  assert event(**b)["source_data_time_status"]=="KNOWN"
  for change in (dict(volume_zhang=999),dict(evg5=2.49,f10_projected_zhang=4980),
                 dict(evg1=2.49,f10_projected_zhang=4980)):
   # EVG values must agree with both denominators; adjust both for low-EVG checks.
   if "evg5" in change:change.update(evg1=2.49)
   if "evg1" in change:change.update(evg5=2.49)
   assert event(**dict(base,**change)) is None
  for change in (dict(source_data_time="2026-10-12T09:11:00+08:00"),
                 dict(observed_at="2026-10-12T09:10:10"),
                 dict(evg5=5.0)):
   try:event(**dict(base,**change));raise AssertionError("bad input accepted")
   except ValueError:pass
 print("PASS | UNKNOWN source timestamp preserved; known timestamp validated")
 print("PASS | EVG consistency, strict AND, exclusive first-write, dedupe, provenance")
 print("TEMP ONLY | NO NETWORK | NO PRODUCTION WRITES | NOT LIVE CAPTURE")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--selftest",action="store_true");a=p.parse_args()
 if not a.selftest:p.error("Research only; use --selftest")
 selftest()
