#!/usr/bin/env python3
"""Read-only FLOW gate audit for 2026-10-22; not a full snapshot/queue replay."""
import json,sqlite3,urllib.request,types,sys
from pathlib import Path
from datetime import datetime
from collections import Counter
ROOT=Path("/var/data/stock-alert");DAY="2026-10-22"
SHA="1587dccc3fef49ea47458173e832d145c50490d9"
URL=f"https://raw.githubusercontent.com/ting78963/stock-alert/{SHA}/fugle_a_scanner_v2_4.py"
mod=types.ModuleType("offline_flow_candidate");mod.__file__=URL;sys.modules[mod.__name__]=mod
exec(compile(urllib.request.urlopen(URL,timeout=30).read().decode(),URL,"exec"),mod.__dict__)
adapter=mod.FugleAdapter.__new__(mod.FugleAdapter);adapter.history_cache={};adapter._estvr5_cache={}
adapter.daily_history=lambda *a: (_ for _ in ()).throw(RuntimeError("NETWORK_FALLBACK_FORBIDDEN"))
adapter.historical_json=adapter.daily_history
scan=mod.Scanner.__new__(mod.Scanner);scan.adapter=adapter
con=sqlite3.connect(f"file:{ROOT/'shared_history_stage_v1.sqlite3'}?mode=ro",uri=True)
print("symbol,first_flow_gate_minute,first_arm_minute,first_no_vcp_price_gate_minute,queue_tier_at_gate,status,reason")
counts=Counter()
for file in sorted((ROOT/"f15_eod/trajectory_v1"/DAY).glob("*.json")):
 if file.name=="manifest.json":continue
 d=json.loads(file.read_text(encoding="utf-8"));sym=str(d["identity"]["stock_id"])
 rows=con.execute("SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 60",(sym,DAY)).fetchall()
 if len(rows)<60:print(f"{sym},,,,,UNKNOWN,DAILY_MISSING");counts["UNKNOWN"]+=1;continue
 prev=float(rows[0][1]);ma20=sum(float(x[1]) for x in rows[:20])/20;avg5=sum(float(x[2]) for x in rows[:5])/5
 firstgate=firstarm=firstprice=tier=None;error=None
 for b in sorted(d.get("trajectory_raw_1m",[]),key=lambda x:str(x.get("minute",""))):
  tm=str(b["minute"])[:5];vol=float(b["cum_volume"]);price=float(b.get("close") or 0)
  if price<=0 or prev<=0:error="MINUTE_CLOSE_OR_PREVCLOSE_INVALID";break
  dt=datetime.fromisoformat(DAY+"T"+tm+":00+08:00")
  vmin=scan.liquidity_minimum(dt)
  if vmin is None or vol<vmin or price<=prev:continue
  if firstgate is None:
   firstgate=tm
   raw=vol/avg5 if avg5>0 else 0
   tier="SPECIAL" if raw>=1.5 else "Q"+str(scan.queue_priority(raw,vol))
  status,reason,m=scan.snapshot_surge_decision({"stock_id":sym,"date":DAY,"total_volume":vol},DAY,dt)
  # FLOW arm threshold is OR(estVR5>=1.5, EVG1>=1.5), distinct from SURGE's 2.5.
  if status=="UNKNOWN":error=reason;break
  if m:
   armed=m["estimated_vr5"]>=1.5 or m["evg1"]>=1.5
   if armed and firstarm is None:firstarm=tm
   if armed and price>=ma20 and (price/prev-1)*100>=3 and firstprice is None:firstprice=tm
 status="UNKNOWN" if error else ("PRICE_GATE" if firstprice else "ARM_ONLY" if firstarm else "MOTHER_ONLY" if firstgate else "NO_MOTHER_GATE")
 counts[status]+=1
 print(f"{sym},{firstgate or ''},{firstarm or ''},{firstprice or ''},{tier or ''},{status},{error or 'METADATA_QUEUE_HANDOFF_NOT_REPLAYED'}")
con.close()
print("SUMMARY",json.dumps({"date":DAY,"counts":dict(counts),"scope":"F15-selected minute-close proxy; rising computed against previous close, not Fugle snapshot change_rate; metadata, FIFO, armed persistence, 5-second handoff not replayed. PRICE_GATE is NOT confirmed FLOW handoff; no writes or LINE"},ensure_ascii=False))
