#!/usr/bin/env python3
"""2026-10-22 real minute-input integrated scan_once replay. Read-only; never bridge/LINE.
Uses genuine candidate Scanner.scan_once, StrongSelector, SURGE/FLOW F10 and pinned VCP.
Minute bars are F15-selected subset, not complete 5-second snapshots.
"""
import contextlib,datetime,io,json,sqlite3,sys,tempfile,types,urllib.request
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
ROOT=Path("/var/data/stock-alert");DAY="2026-10-22"
SHA="b1c57eed456b01a02ffcfb980f9a8bb882ae5e32"
BASE=f"https://raw.githubusercontent.com/ting78963/stock-alert/{SHA}/"
def fetch(p):return urllib.request.urlopen(BASE+p,timeout=30).read()
with tempfile.TemporaryDirectory(prefix="a-real-replay-") as temp:
 base=Path(temp)
 for p in ["vcp_a.py","vcp_scan_once_adapter.py","research/vcp_integration_audit_lab_20261018/scanner_7413a49.py.txt"]:
  dest=base/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(fetch(p))
 sys.path.insert(0,temp)
 import vcp_scan_once_adapter
 source=fetch("fugle_a_scanner_v2_4.py").decode()
 mod=types.ModuleType("offline_real_a");mod.__file__=BASE+"fugle_a_scanner_v2_4.py";sys.modules[mod.__name__]=mod
 exec(compile(source,mod.__file__,"exec"),mod.__dict__)
 from vcp_scan_once_adapter import VcpScanOnceRuntime
 con=sqlite3.connect(f"file:{ROOT/'shared_history_stage_v1.sqlite3'}?mode=ro",uri=True)
 data={}
 for f in sorted((ROOT/"f15_eod/trajectory_v1"/DAY).glob("*.json")):
  if f.name=="manifest.json":continue
  obj=json.loads(f.read_text(encoding="utf-8"));sym=str(obj["identity"]["stock_id"])
  rows=con.execute("SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 60",(sym,DAY)).fetchall()
  if len(rows)!=60:raise SystemExit(f"STOP: {sym} prior60 incomplete")
  hist=[SimpleNamespace(date=str(d),close=float(c),volume_zhang=float(v)) for d,c,v in reversed(rows)]
  mins={str(b["minute"])[:5]:b for b in obj.get("trajectory_raw_1m",[])}
  data[sym]={"minutes":mins,"bars":hist,"prev":float(rows[0][1])}
 if not data:raise SystemExit("STOP: no 10/22 trajectory")
 meta={}
 for p in [ROOT/"a_f11_metadata_v1.json",ROOT/"a_scanner_v2/a_f11_metadata_v1.json"]:
  if p.is_file():
   o=json.loads(p.read_text(encoding="utf-8"))
   for d in (o,o.get("symbols"),o.get("data"),o.get("metadata")):
    if isinstance(d,dict):meta.update({k:v for k,v in d.items() if isinstance(v,dict)})
 if any(s not in meta for s in data):raise SystemExit("STOP: F11 metadata missing for "+",".join(s for s in data if s not in meta))
 clock=[datetime.datetime.fromisoformat(DAY+"T09:00:00+08:00")]
 mod.now_tw=lambda:clock[0]
 mod.iso_now=lambda:clock[0].isoformat()
 events=[];queues=[]
 mod.append_event=lambda x:events.append(x)
 mod.append_queue_shadow=lambda day,x:queues.append(x)
 mod.record_a_scan_mother_identity=lambda *a:None
 mod.save_json_atomic=lambda *a,**kw:None
 mod.STATE_FILE="NO_DISK_WRITES"
 mod.F11_OFFLINE_STAGING_ENABLED=False
 class Adapter:
  def __init__(self):
   self.real=mod.FugleAdapter.__new__(mod.FugleAdapter)
   self.real.history_cache={};self.real._estvr5_cache={}
   self.real.daily_history=lambda *a:(_ for _ in ()).throw(RuntimeError("NETWORK_DISABLED"))
   self.real.historical_json=self.real.daily_history
   self.snap=[]
  def snapshot(self):return self.snap
  def ticker(self,s):return meta[s]
  def daily_history_local_ready(self,s,d):return data[s]["bars"]
  def prepare_f10_cache_only(self,*a):pass
  def has_complete_f10_cache_only(self,s,d):
   with sqlite3.connect(f"file:{ROOT/'f10_baseline_v1.sqlite3'}?mode=ro",uri=True) as c:
    rows=c.execute("SELECT full FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(s,d)).fetchall()
   return len(rows)==10 and all(bool(x[0]) for x in rows)
  def estimated_vr5_parts(self,*a):return mod.FugleAdapter.estimated_vr5_parts(self.real,*a)
 class Worker:
  def submit(self,*a):return False
 scan=mod.Scanner.__new__(mod.Scanner)
 scan.adapter=Adapter();scan.selector=mod.StrongSelector.__new__(mod.StrongSelector)
 scan.layered_a_enabled=True;scan.wait_data_worker=Worker()
 scan.state={"discovered":{},"queue_waiting":{},"volume_armed":{},"layered_vcp_state":{}}
 scan._layered_vcp_runtime=lambda:VcpScanOnceRuntime(lambda:clock[0],scan.state.get("layered_vcp_state",{}))
 scan._layered_vcp_inputs=lambda sym,d:(meta[sym],data[sym]["bars"],None)
 scan.apply_wait_data_results=lambda:None
 receipts=[]
 def handoff(hit,day):
  sym=hit["code"]
  if scan.already_sent(day,sym):return False
  receipts.append((clock[0].strftime("%H:%M"),sym,hit["source"]))
  scan.state["discovered"].setdefault(day,{})[sym]=hit
  return True
 scan.handoff_hit=handoff
 times=sorted({t for x in data.values() for t in x["minutes"]})
 latest={}
 errors=[]
 for minute in times:
  clock[0]=datetime.datetime.fromisoformat(DAY+"T"+minute+":00+08:00")
  snaps=[]
  for sym,x in data.items():
   if minute in x["minutes"]:latest[sym]=x["minutes"][minute]
   if sym not in latest:continue
   b=latest[sym];close=float(b.get("close") or 0)
   if close<=0:continue
   snaps.append({"stock_id":sym,"name":sym,"date":DAY,"total_volume":float(b["cum_volume"]),"close":close,"change_rate":round((close/x["prev"]-1)*100,4)})
  scan.adapter.snap=snaps
  if not snaps:continue
  try:
   with contextlib.redirect_stdout(io.StringIO()):scan.scan_once()
  except Exception as exc:
   errors.append((minute,type(exc).__name__,str(exc)[:180]));break
 con.close()
 print("date,minute,symbol,source")
 for minute,sym,route in receipts:print(f"{DAY},{minute},{sym},{route}")
 print("SUMMARY",json.dumps({"minute_snapshots":len(times),"symbols":len(data),"receipts":len(receipts),"routes":dict(Counter(r for _,_,r in receipts)),"candidate_errors":[e for e in events if e.get("type")=="candidate_error"][:12],"fatal":errors,"queue_process_events":sum(e.get("type")=="PROCESS_START" for e in queues),"scope":"Actual Scanner.scan_once, selector, pinned VCP, F10 and daily history; F15-selected 1m observations only, carry-forward for missing minute; historical metadata may not be as-of; no 5s snapshot, disk writes, API, bridge or LINE"},ensure_ascii=False))
 if errors or any(e.get("type")=="candidate_error" for e in events):raise SystemExit("REPLAY_INCOMPLETE: see errors above")
