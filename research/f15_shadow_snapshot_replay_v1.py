#!/usr/bin/env python3
"""F15 shadow A snapshot replay. Research-only; no production imports/network/writes.
Input: JSON array of already obtained A snapshots; offline replay, not live capture.
"""
import argparse,datetime as dt,json,math,sqlite3,sys
from pathlib import Path
from zoneinfo import ZoneInfo
TW=ZoneInfo("Asia/Taipei")
def f10(con,sym,date,cut):
 rows=con.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(sym,date)).fetchall()[::-1]
 if len(rows)!=10:return None,"F10_INCOMPLETE"
 days=[];prev=""
 for ds,full,raw in rows:
  if ds<=prev:return None,"BAD_DAY_ORDER"
  prev=ds
  try:pts=json.loads(raw);full=float(full)
  except (ValueError,TypeError):return None,"MALFORMED"
  if not pts or not math.isfinite(full) or full<=0:return None,"INVALID_FULL"
  last=-1.;ts_prev="";at=0.
  for p in pts:
   if not isinstance(p,list) or len(p)!=2:return None,"BAD_POINT"
   t,v=str(p[0]),float(p[1])
   if t<=ts_prev or not math.isfinite(v) or v<last or v<0:return None,"BAD_CURVE"
   ts_prev=t;last=v
   if t<=cut:at=v
  if abs(last-full)>1e-9:return None,"FULL_MISMATCH"
  days.append((ds,full,at))
 fraction=sum(at/full for _,full,at in days)/10
 if fraction<=0:return None,"F10_ZERO_AT_CUTOFF"
 avg=sum(x[1] for x in days[-5:])/5
 return (fraction,avg,days[-1][1],[x[0] for x in days]),None
def run(snaps,db,observed_at):
 stamp=dt.datetime.fromisoformat(observed_at)
 if stamp.tzinfo is None:raise ValueError("observed_at must have timezone")
 tw=stamp.astimezone(TW);date=tw.date().isoformat();cut=tw.strftime("%H:%M:00")
 if not isinstance(snaps,list) or not snaps:raise ValueError("nonempty snapshot array required")
 path=Path(db)
 if not path.is_file():raise ValueError("F10 DB missing")
 con=sqlite3.connect("file:"+str(path.resolve())+"?mode=ro",uri=True,timeout=3)
 results=[];stats={"snapshot_rows":len(snaps),"under_1000":0,"eligible":0,"not_eligible":0,"missing":0,"invalid":0}
 try:
  con.execute("PRAGMA query_only=ON")
  seen=set()
  for s in snaps:
   if not isinstance(s,dict):stats["invalid"]+=1;continue
   sym=str(s.get("stock_id") or "")
   if not sym.isdigit() or len(sym)<4 or len(sym)>6 or sym in seen:stats["invalid"]+=1;continue
   seen.add(sym)
   rawdate=str(s.get("date") or "")[:10]
   if rawdate!=date:stats["invalid"]+=1;continue
   try:vol=float(s.get("total_volume"))
   except (ValueError,TypeError):stats["invalid"]+=1;continue
   if not math.isfinite(vol) or vol<0:stats["invalid"]+=1;continue
   if vol<1000:stats["under_1000"]+=1;continue
   base,reason=f10(con,sym,date,cut)
   if reason:
    stats["missing"]+=1
    results.append({"stock_id":sym,"status":reason})
    continue
   fraction,avg,prev,days=base
   projected=vol/fraction
   evg5=projected/avg;evg1=projected/prev
   passed=evg5>=2.5 and evg1>=2.5
   stats["eligible" if passed else "not_eligible"]+=1
   results.append({"stock_id":sym,"status":"SHADOW_ELIGIBLE" if passed else "BELOW_EVG_GATE","cum_volume_zhang":vol,"f10":fraction,"projected_zhang":projected,"evg5":evg5,"evg1":evg1,"baseline_days":days})
 finally:con.close()
 return {"mode":"OFFLINE_SNAPSHOT_REPLAY_ONLY","observed_at":observed_at,"cutoff_proxy":cut,"cutoff_is_market_timestamp":False,"date":date,"stats":stats,"rows":results}
def main():
 p=argparse.ArgumentParser();p.add_argument("--snapshot-json",required=True);p.add_argument("--db",default="/var/data/stock-alert/f10_baseline_v1.sqlite3");p.add_argument("--observed-at",required=True);a=p.parse_args()
 snaps=json.loads(Path(a.snapshot_json).read_text(encoding="utf-8"))
 print(json.dumps(run(snaps,a.db,a.observed_at),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
