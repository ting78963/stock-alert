#!/usr/bin/env python3
"""F15 research-only V2 snapshot bridge. No network, no production imports, no persistence.
Caller passes an ALREADY OBTAINED snapshot list and its observed timestamp.
This does NOT certify market-data time, and does not modify A/B/LINE.
"""
import argparse,datetime as dt,json
from pathlib import Path
from f15_shadow_snapshot_replay_v1 import run
from f15_early_handoff_recorder_v2 import event

def bridge(snaps,db,observed_at):
 replay=run(snaps,db,observed_at)
 candidates=[]
 for r in replay["rows"]:
  if r["status"]!="SHADOW_ELIGIBLE":continue
  # Reconstruct denominators from the independently computed projection.
  # For live use, these must also be checked against the original F10 baseline.
  f10=r["f10"]
  if f10<=0:raise ValueError("invalid F10")
  projected=r["projected_zhang"]
  avg5=projected/r["evg5"]
  prev1=projected/r["evg1"]
  e=event(date=replay["date"],stock_id=r["stock_id"],observed_at=observed_at,
    volume_zhang=r["cum_volume_zhang"],evg5=r["evg5"],evg1=r["evg1"],
    f10_projected_zhang=projected,prior5_avg_zhang=avg5,
    prior1_volume_zhang=prev1,source="A_SNAPSHOT_OFFLINE_REPLAY",
    source_version="f15_shadow_bridge_v2",source_data_time=None)
  if e is None:raise ValueError("eligible replay rejected by recorder")
  candidates.append(e)
 return {"mode":"DRY_RUN_NO_PERSISTENCE","stats":replay["stats"],
         "first_observed_at_is_market_time":False,"candidate_events":candidates}

def selftest():
 import sqlite3,tempfile
 with tempfile.TemporaryDirectory(prefix="f15_bridge_v2_") as temp:
  db=Path(temp)/"f10.sqlite3"
  with sqlite3.connect(db) as con:
   con.execute("CREATE TABLE f10_day(symbol TEXT,day TEXT,full REAL,pts_json TEXT)")
   for i in range(10):
    d=(dt.date(2026,9,20)+dt.timedelta(days=i)).isoformat()
    con.execute("INSERT INTO f10_day VALUES(?,?,?,?)",
       ("1326",d,2000,json.dumps([["09:00:00",100],["09:10:00",400],["13:30:00",2000]])))
  out=bridge([{"stock_id":"1326","date":"2026-10-01","total_volume":1100}],str(db),"2026-10-01T09:10:10+08:00")
  assert out["stats"]["eligible"]==1 and len(out["candidate_events"])==1
  e=out["candidate_events"][0]
  assert e["source_data_time_status"]=="UNKNOWN" and e["market_first_eligible_certified"] is False
  assert abs(e["evg5"]-2.75)<1e-9 and e["first_shadow_observed_at"]=="2026-10-01T09:10:10+08:00"
 print("PASS | snapshot -> F10 -> strict AND -> V2 event, source time UNKNOWN")
 print("DRY RUN ONLY | NO NETWORK | NO PERSISTENCE | NO A/B/LINE")
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--selftest",action="store_true")
 p.add_argument("--snapshot-json")
 p.add_argument("--db",default="/var/data/stock-alert/f10_baseline_v1.sqlite3")
 p.add_argument("--observed-at")
 a=p.parse_args()
 if a.selftest:selftest();return
 if not a.snapshot_json or not a.observed_at:p.error("use --selftest or both --snapshot-json and --observed-at")
 print(json.dumps(bridge(json.loads(Path(a.snapshot_json).read_text(encoding="utf-8")),a.db,a.observed_at),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
