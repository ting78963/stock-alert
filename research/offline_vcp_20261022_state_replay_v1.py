#!/usr/bin/env python3
"""Oct-22 isolated minute-by-minute VCP state replay; never writes production state."""
import json,sqlite3,tempfile,urllib.request,sys,hashlib
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace
from collections import Counter
ROOT=Path("/var/data/stock-alert"); DAY="2026-10-22"
SHA="8e8ac8976e764ebb1d428332ef4f87dae05b36f2"
BASE=f"https://raw.githubusercontent.com/ting78963/stock-alert/{SHA}/"
PIN="research/vcp_integration_audit_lab_20261018/scanner_7413a49.py.txt"
paths=["vcp_a.py","vcp_scan_once_adapter.py",PIN]
db=ROOT/"shared_history_stage_v1.sqlite3"
if not db.is_file():raise SystemExit("STOP: daily history absent")
meta_paths=[ROOT/"a_f11_metadata_v1.json",ROOT/"a_scanner_v2/a_f11_metadata_v1.json"]
def lookup_meta(s):
 for path in meta_paths:
  if not path.is_file():continue
  try: obj=json.loads(path.read_text(encoding="utf-8"))
  except Exception:continue
  for d in (obj,obj.get("data") if isinstance(obj,dict) else None,obj.get("metadata") if isinstance(obj,dict) else None):
   if isinstance(d,dict):
    x=d.get(s)
    if isinstance(x,dict):return x
 return None
with tempfile.TemporaryDirectory(prefix="offline-vcp-") as tmp:
 base=Path(tmp)
 for rel in paths:
  raw=urllib.request.urlopen(BASE+rel,timeout=30).read()
  dest=base/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
 sys.path.insert(0,tmp)
 from vcp_scan_once_adapter import VcpScanOnceRuntime
 import vcp_a
 selector=vcp_a.namespace("offline_vcp_selector")["StrongSelector"].__new__(vcp_a.namespace("offline_vcp_selector_2")["StrongSelector"])
 con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
 stats=Counter()
 print("symbol,first_800,metadata,minute_rows,vcp_handoff_first,status,reason")
 for file in sorted((ROOT/"f15_eod/trajectory_v1"/DAY).glob("*.json")):
  if file.name=="manifest.json":continue
  data=json.loads(file.read_text(encoding="utf-8"));sym=str(data["identity"]["stock_id"])
  minute=sorted(data.get("trajectory_raw_1m",[]),key=lambda b:str(b.get("minute","")))
  eligible=[x for x in minute if float(x.get("cum_volume",0))>=800]
  if not eligible:stats["BELOW_800"]+=1;continue
  first=str(eligible[0].get("minute",""))[:5]
  rows=con.execute("SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 60",(sym,DAY)).fetchall()
  meta=lookup_meta(sym)
  if len(rows)<60:
   print(f"{sym},{first},UNKNOWN,{len(minute)},,UNKNOWN,DAILY_INCOMPLETE");stats["DAILY_INCOMPLETE"]+=1;continue
  if not isinstance(meta,dict):
   print(f"{sym},{first},MISSING,{len(minute)},,UNKNOWN,METADATA_NOT_AVAILABLE");stats["METADATA_MISSING"]+=1;continue
  if not selector.meta_ok(meta):
   print(f"{sym},{first},REJECTED,{len(minute)},,FAIL,METADATA_REJECTED");stats["METADATA_REJECTED"]+=1;continue
  history=[SimpleNamespace(date=str(d),close=float(c),volume_zhang=float(v)) for d,c,v in reversed(rows)]
  avg=sum(float(v) for _,_,v in rows[:5])/5
  clock=[datetime.fromisoformat(DAY+"T09:00:00+08:00")]
  runtime=VcpScanOnceRuntime(lambda:clock[0],{})
  hit=None;error=None
  for bar in eligible:
   tm=str(bar.get("minute",""))[:5]
   try:clock[0]=datetime.fromisoformat(DAY+"T"+tm+":00+08:00")
   except ValueError:error="INVALID_MINUTE";break
   volume=float(bar["cum_volume"])
   close=float(bar.get("close") or 0)
   if close<=0:error="MISSING_CLOSE";break
   snap={"stock_id":sym,"date":DAY,"total_volume":volume,"close":close}
   try:
    result=runtime.evaluate(snap,history,meta,volume/avg if avg>0 else 0,0 if avg>0 and volume/avg>=1.5 else 4)
   except Exception as exc:
    error=type(exc).__name__+":"+str(exc)[:85];break
   if result.get("proposals"):hit=tm;break
  status="UNKNOWN" if error else ("PASS" if hit else "NO_HANDOFF")
  stats[status]+=1
  print(f"{sym},{first},VALID,{len(minute)},{hit or ''},{status},{error or ('VCP_PROPOSAL' if hit else 'NO_PROPOSAL_IN_REPLAY')}")
 con.close()
 print("SUMMARY",json.dumps({"date":DAY,"counts":dict(stats),"scope":"F15-selected stocks only; minute-close observations, zero initial VCP state; missing historical state may change outcomes; metadata must be verified; not exact production 5-second replay; no LINE or production state writes"},ensure_ascii=False))
