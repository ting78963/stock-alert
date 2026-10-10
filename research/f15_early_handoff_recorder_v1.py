#!/usr/bin/env python3
"""F15 early-handoff research recorder V1.
Standalone, stdlib-only. Does NOT import A/B, call APIs, or send notifications.
Default command is self-test using a temporary directory. Production capture is NOT wired.
"""
from __future__ import annotations
import argparse,datetime as dt,json,os,tempfile
from pathlib import Path
from zoneinfo import ZoneInfo
TZ=ZoneInfo("Asia/Taipei")
THRESHOLD={"volume_zhang":1000,"evg5":2.5,"evg1":2.5}
SCHEMA="f15_early_handoff_candidate_v1"
def require(cond,msg):
 if not cond:raise ValueError(msg)
def event(date,stock_id,market_minute,observed_at,volume_zhang,evg5,evg1,
          f10_projected_zhang,prior5_avg_zhang,prior1_volume_zhang,source,
          source_version,source_data_time=None):
 require(isinstance(date,str) and dt.date.fromisoformat(date).isoformat()==date,"invalid date")
 require(isinstance(stock_id,str) and stock_id.isdigit() and len(stock_id) in (4,5,6),"invalid stock_id")
 require(isinstance(market_minute,str) and len(market_minute)==5,"invalid minute")
 dt.time.fromisoformat(market_minute)
 require(isinstance(observed_at,str),"missing observed_at")
 ts=dt.datetime.fromisoformat(observed_at)
 require(ts.tzinfo is not None and ts.utcoffset() is not None,"observed_at must be timezone-aware")
 require(ts.astimezone(TZ).date().isoformat()==date,"observed_at/date mismatch")
 for k,v in {"volume":volume_zhang,"evg5":evg5,"evg1":evg1,"f10":f10_projected_zhang,
             "prior5":prior5_avg_zhang,"prior1":prior1_volume_zhang}.items():
  require(isinstance(v,(int,float)) and not isinstance(v,bool) and 0<=float(v)<1e12,k+" invalid")
 require(prior5_avg_zhang>0 and prior1_volume_zhang>0,"baseline zero")
 require(source and source_version,"missing provenance")
 require(source_data_time is not None,"source_data_time required to establish causal data availability")
 src_ts=dt.datetime.fromisoformat(source_data_time)
 require(src_ts.tzinfo is not None and src_ts.utcoffset() is not None,"source_data_time timezone required")
 require(src_ts<=ts,"source data timestamp later than observation")
 # Only qualifying candidates are recorded. Do not infer B outcomes from this.
 if not(volume_zhang>=1000 and evg5>=2.5 and evg1>=2.5):return None
 return {"schema":SCHEMA,"date":date,"stock_id":stock_id,"market_minute":market_minute,
         "observed_at":observed_at,"source_data_time":source_data_time,
         "cum_volume_zhang":volume_zhang,"evg5":evg5,"evg1":evg1,
         "f10_projected_zhang":f10_projected_zhang,"prior5_avg_zhang":prior5_avg_zhang,
         "prior1_volume_zhang":prior1_volume_zhang,"source":source,
         "source_version":source_version,"thresholds":THRESHOLD.copy(),
         "mode":"SHADOW_ONLY","b_handoff_performed":False}
def append_once(root,record):
 """One file per stock-day; atomic exclusive create; no overwrites.
 Caller must only invoke on real-time data; this method does not certify timing.
 """
 require(record is not None and record.get("schema")==SCHEMA,"invalid event")
 date=record["date"];stock=record["stock_id"]
 require(dt.date.fromisoformat(date).isoformat()==date and stock.isdigit(),"invalid identity")
 folder=Path(root)/"early_handoff_v1"/date
 folder.mkdir(parents=True,exist_ok=True)
 target=folder/(stock+".json")
 payload=(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
 try:
  with target.open("xb") as f:
   f.write(payload);f.flush();os.fsync(f.fileno())
  return "CREATED",target
 except FileExistsError:
  existing=json.loads(target.read_text(encoding="utf-8"))
  require(existing.get("date")==date and existing.get("stock_id")==stock and existing.get("schema")==SCHEMA,"identity conflict")
  return "ALREADY_EXISTS",target
def selftest():
 with tempfile.TemporaryDirectory(prefix="f15_eh_test_") as temp:
  base={"date":"2026-10-12","stock_id":"1326","market_minute":"09:09",
        "observed_at":"2026-10-12T09:09:10+08:00","source_data_time":"2026-10-12T09:09:05+08:00",
        "volume_zhang":1200,"evg5":3.1,"evg1":2.8,"f10_projected_zhang":6000,
        "prior5_avg_zhang":1935.48387,"prior1_volume_zhang":2142.857,
        "source":"TEST_FIXTURE","source_version":"test"}
  e=event(**base);require(e is not None,"positive gate failed")
  s,p=append_once(temp,e);require(s=="CREATED","first create failed")
  s,_=append_once(temp,e);require(s=="ALREADY_EXISTS","dedupe failed")
  require(json.loads(p.read_text())==e,"roundtrip failed")
  for field,value in (("volume_zhang",999),("evg5",2.49),("evg1",2.49)):
   b=dict(base);b[field]=value;require(event(**b) is None,"AND gate failed "+field)
  b=dict(base);b["source_data_time"]="2026-10-12T09:10:00+08:00"
  try:event(**b);raise AssertionError("future timestamp accepted")
  except ValueError:pass
  b=dict(base);b["stock_id"]="9999";b["market_minute"]="09:11"
  s,_=append_once(temp,event(**b));require(s=="CREATED","other identity failed")
  require(len(list((Path(temp)/"early_handoff_v1"/base["date"]).glob("*.json")))==2,"file count mismatch")
 print("SELFTEST PASS | strict AND, duplicate stock-day, separate identity, timezone, causal timestamp, JSON persistence")
 print("NO PRODUCTION WRITES | NO NETWORK | NO A/B IMPORTS")
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument("--selftest",action="store_true",help="run isolated temporary-directory tests")
 args=ap.parse_args()
 if not args.selftest:ap.error("Research module is not wired to production. Run --selftest only.")
 selftest()
if __name__=="__main__":main()
