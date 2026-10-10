#!/usr/bin/env python3
"""F15 shadow replay -> recorder integration self-test. Temporary files only."""
import datetime as dt,json,sqlite3,tempfile
from pathlib import Path
from f15_shadow_snapshot_replay_v1 import run
from f15_early_handoff_recorder_v1 import event,append_once
def main():
 with tempfile.TemporaryDirectory(prefix="f15_shadow_integration_") as tmp:
  root=Path(tmp);db=root/"baseline.sqlite3"
  with sqlite3.connect(db) as con:
   con.execute("CREATE TABLE f10_day(symbol TEXT,day TEXT,full REAL,pts_json TEXT)")
   for i in range(10):
    day=(dt.date(2026,9,20)+dt.timedelta(days=i)).isoformat()
    for sym in ("1326","9999"):
     con.execute("INSERT INTO f10_day VALUES(?,?,?,?)",(sym,day,2000,json.dumps([["09:00:00",100],["09:10:00",400],["13:30:00",2000]])))
  stamp="2026-10-01T09:10:10+08:00"
  snaps=[{"stock_id":"1326","date":"2026-10-01","total_volume":1100},{"stock_id":"9999","date":"2026-10-01","total_volume":999}]
  r=run(snaps,str(db),stamp)
  assert r["stats"]["eligible"]==1 and r["stats"]["under_1000"]==1,r["stats"]
  candidate=next(x for x in r["rows"] if x["status"]=="SHADOW_ELIGIBLE")
  assert candidate["stock_id"]=="1326" and abs(candidate["evg5"]-2.75)<1e-9
  # An offline replay cannot certify a market data timestamp. Test recorder using
  # a synthetic, explicitly identified timestamp only; never save as a live event.
  e=event(date=r["date"],stock_id=candidate["stock_id"],market_minute="09:10",
    observed_at=stamp,volume_zhang=candidate["cum_volume_zhang"],
    evg5=candidate["evg5"],evg1=candidate["evg1"],
    f10_projected_zhang=candidate["projected_zhang"],
    prior5_avg_zhang=2000,prior1_volume_zhang=2000,
    source="SYNTHETIC_INTEGRATION_TEST",source_version="v1",
    source_data_time="2026-10-01T09:10:00+08:00")
  assert e and e["mode"]=="SHADOW_ONLY"
  status,p=append_once(root,e);assert status=="CREATED"
  status,_=append_once(root,e);assert status=="ALREADY_EXISTS"
  assert json.loads(p.read_text(encoding="utf-8"))["source"]=="SYNTHETIC_INTEGRATION_TEST"
  assert not (root/"f15_eod").exists()
 print("PASS | snapshot -> strict AND -> event -> first-write -> dedupe")
 print("PASS | below-1000 ignored; F10 from temp SQLite; synthetic provenance")
 print("TEMP ONLY | NO FUGLE | NO A/B/LINE | NOT LIVE CAPTURE")
if __name__=="__main__":main()
