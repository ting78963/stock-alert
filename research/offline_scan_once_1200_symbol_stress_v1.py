#!/usr/bin/env python3
"""2026-10-22 isolated per-scan timing audit. Read-only; never bridge/LINE.
Uses genuine candidate Scanner.scan_once, StrongSelector, SURGE/FLOW F10 and pinned VCP.
Minute bars are F15-selected subset, not complete 5-second snapshots.
"""
import contextlib,datetime,io,json,sqlite3,sys,tempfile,types,urllib.request,time,statistics,os,traceback
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
 # Select original histories with complete F10 curves, before cloning.
 with sqlite3.connect(f"file:{ROOT/'f10_baseline_v1.sqlite3'}?mode=ro",uri=True) as f10:
  eligible=[]
  for sym in data:
   with sqlite3.connect(f"file:{ROOT/'f10_baseline_v1.sqlite3'}?mode=ro",uri=True) as check:
    rows=check.execute("SELECT full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(sym,DAY)).fetchall()
   if len(rows)==10 and all(float(full)>0 and bool(pts) for full,pts in rows):eligible.append(sym)
 if not eligible:raise SystemExit("STOP: no complete F10 source symbols")
 data={sym:data[sym] for sym in eligible}
 print("STRESS_F10_SOURCES",json.dumps({"eligible":eligible,"excluded":9-len(eligible)}))
 target=int(os.environ.get("A_STRESS_SYMBOLS","1200"))
 if target<9 or target>2000:raise SystemExit("STOP: symbol count must be 9..2000")
 originals=list(data);alias={}
 for n in range(1000,9999):
  if len(data)>=target:break
  sid=f"{n:04d}"
  if sid in data:continue
  src=originals[len(alias)%len(originals)]
  alias[sid]=src;data[sid]=data[src];meta[sid]=dict(meta[src])
 print("STRESS_SETUP",json.dumps({"symbols":len(data),"original_real_symbols":len(originals),"replicated_symbols":len(alias),"synthetic":True}))
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
   s=alias.get(s,s)
   with sqlite3.connect(f"file:{ROOT/'f10_baseline_v1.sqlite3'}?mode=ro",uri=True) as c:
    rows=c.execute("SELECT full FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(s,d)).fetchall()
   return len(rows)==10 and all(bool(x[0]) for x in rows)
  def estimated_vr5_parts(self,s,*a):return mod.FugleAdapter.estimated_vr5_parts(self.real,alias.get(s,s),*a)
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
 times=[t for t in times if t in ("09:10","10:36","12:41")]
 latest={}
 errors=[]
 timings=[]
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
   tick=time.perf_counter()
   with contextlib.redirect_stdout(io.StringIO()):scan.scan_once()
   timings.append((minute,(time.perf_counter()-tick)*1000,len(snaps)))
  except Exception as exc:
   print("STRESS_EXCEPTION_TRACEBACK",traceback.format_exc(limit=15),flush=True)
   errors.append((minute,type(exc).__name__,str(exc)[:180]));break
 # Audit actual FLOW processing order against same-scan FIFO control rank.
 process=[q for q in queues if q.get("type")=="PROCESS_START"]
 by_scan={}
 for q in process:by_scan.setdefault(q["scan_id"],[]).append(q)
 violations=[]
 for sid,group in by_scan.items():
  ranks=[int(q["control_fifo_rank"]) for q in group]
  if ranks!=sorted(ranks):violations.append({"scan":sid,"ranks":ranks})
 unique_receipts=len({s for _,s,_ in receipts})==len(receipts)
 ms=sorted(t[1] for t in timings)
 if ms:
  p95=ms[min(len(ms)-1,int(0.95*(len(ms)-1)))]
  worst=sorted(timings,key=lambda x:x[1],reverse=True)[:5]
  print("TIMING_AUDIT",json.dumps({"scans":len(ms),"mean_ms":round(statistics.mean(ms),2),"median_ms":round(statistics.median(ms),2),"p95_ms":round(p95,2),"max_ms":round(ms[-1],2),"over_5000ms":sum(v>5000 for v in ms),"worst_5":[{"minute":m,"elapsed_ms":round(v,2),"symbols":n} for m,v,n in worst],"scope":"1200 synthetic symbol identities cloned from 9 real histories; stub snapshot/bridge; excludes network and actual full-market data"},ensure_ascii=False))
 print("FIFO_PROCESS_START")
 for q in process:
  print(json.dumps({"scan":q["scan_id"],"symbol":q["symbol"],"priority":q["priority"],"entered_at":q["queue_entered_at"],"fifo_rank":q["control_fifo_rank"],"volume_rank":q["candidate_volume_rank"]},ensure_ascii=False))
 print("FIFO_AUDIT",json.dumps({"process_events":len(process),"scans_with_process":len(by_scan),"ordering_violations":violations,"unique_receipts":unique_receipts,"note":"Only observed PROCESS_START; does not prove FIFO under simultaneous competing same-tier candidates if none occurred"},ensure_ascii=False))
 con.close()
 print("date,minute,symbol,source")
 for minute,sym,route in receipts:print(f"{DAY},{minute},{sym},{route}")
 print("SUMMARY",json.dumps({"minute_snapshots":len(times),"symbols":len(data),"receipts":len(receipts),"routes":dict(Counter(r for _,_,r in receipts)),"candidate_errors":[e for e in events if e.get("type")=="candidate_error"][:12],"fatal":errors,"queue_process_events":sum(e.get("type")=="PROCESS_START" for e in queues),"scope":"Actual Scanner.scan_once, selector, pinned VCP, F10 and daily history; F15-selected 1m observations only, carry-forward for missing minute; historical metadata may not be as-of; no 5s snapshot, disk writes, API, bridge or LINE"},ensure_ascii=False))
 if errors or violations or not unique_receipts or any(e.get("type")=="candidate_error" for e in events):raise SystemExit("REPLAY_INCOMPLETE: see errors above")
 if any(t[1]>5000 for t in timings):raise SystemExit("STRESS_OVER_5S")
