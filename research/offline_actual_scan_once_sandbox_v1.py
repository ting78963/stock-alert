#!/usr/bin/env python3
"""No-I/O test executing actual candidate Scanner.scan_once with injected dependencies.
Synthetic two-scan fixture, not historical 10/22 or full 5-second replay.
"""
import ast,urllib.request,datetime,types,time,contextlib,io
SHA="17ecf3b368ec6b60499194269d5ee68a4c32d141"
url=f"https://raw.githubusercontent.com/ting78963/stock-alert/{SHA}/fugle_a_scanner_v2_4.py"
source=urllib.request.urlopen(url,timeout=30).read().decode()
tree=ast.parse(source)
klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="Scanner")
method=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=="scan_once")
mod=ast.Module(body=[ast.FunctionDef(name="scan_once",args=method.args,body=method.body,decorator_list=[],returns=None,type_comment=None)],type_ignores=[])
ast.fix_missing_locations(mod)
day="2026-10-22";clock=datetime.datetime(2026,10,22,9,35)
logs=[]
def noop(*args,**kwargs):pass
ns={"List":list,"Dict":dict,"Any":object,"Tuple":tuple,"Optional":object,"time":time,"now_tw":lambda:clock,"iso_now":lambda:clock.isoformat(),"AuditStop":RuntimeError,"append_event":lambda e:logs.append(e),"append_queue_shadow":noop,"record_a_scan_mother_identity":noop,"save_json_atomic":noop,"STATE_FILE":"in-memory-only","SURGE_VARIANT":"TEST","RAW_VR5_MIN":2.5,"ESTIMATED_VR5_MIN":1.5,"EVG_MIN_PCT":50,"F11_OFFLINE_STAGING_ENABLED":False}
exec(compile(mod,url,"exec"),ns)
class Bar:
 def __init__(self):self.volume_zhang=1000.;self.close=100.;self.date="2026-10-21"
class Adapter:
 def __init__(self,rows):self.rows=rows
 def snapshot(self):return [dict(x) for x in self.rows]
 def prepare_f10_cache_only(self,*args):pass
 def ticker(self,s):return {"market":"TSE","securityType":"01","industry":"26"}
 def daily_history_local_ready(self,*args):return [Bar() for _ in range(60)]
 def estimated_vr5_parts(self,*args):return (.002,1000.,1000.,[])  # 4000 / .002 / 1000 = 2000: deliberately arm FLOW
class Selector:
 def basic_code_ok(self,s):return len(s)==4 and s.isdigit()
 def meta_ok(self,meta):return True
 def analyze_vcp(self,*args):return {}
 def select_one(self,row,meta,bars):
  return {"code":row["stock_id"],"name":row["stock_id"],"source":"NO_VCP","todayVol":row["total_volume"],"volRatio":2.,"chgPct":row["change_rate"],"price":row["close"]} if row["change_rate"]>=2.5 else None
class Vcp:
 def has_pending(self,*a):return False
 def has_watch(self,*a):return False
 def has_active_track(self,*a):return False
 def evaluate(self,row,*args):
  sym=row["stock_id"]
  return {"proposals":[{"code":sym,"name":sym,"source":"VCP","todayVol":row["total_volume"],"volRatio":2.,"chgPct":row["change_rate"],"price":row["close"]}]} if sym=="7711" else {"proposals":[]}
 def export_state(self):return {}
class Worker:
 def submit(self,*a):return False
class Scanner:
 scan_once=ns["scan_once"]
 layered_a_enabled=True
 wait_data_worker=Worker()
 def __init__(self,rows):
  self.adapter=Adapter(rows);self.selector=Selector();self.vcp=Vcp();self.sent=[];self.failed=set()
  self.state={"discovered":{},"queue_waiting":{},"volume_armed":{}}
 def _layered_vcp_runtime(self):return self.vcp
 def _layered_vcp_inputs(self,*args):return {},[Bar() for _ in range(60)],None
 def liquidity_minimum(self,*args):return 2000.
 def queue_priority(self,vr,vol):return 0 if vr>=2.5 else (1 if vol>=5000 else 2 if vol>=4000 else 3 if vol>=3000 else 4)
 def queue_entered_at(self,d,s):return "09:35:00"
 def apply_wait_data_results(self):pass
 def already_sent(self,d,s):return s in self.state["discovered"].get(d,{})
 def snapshot_surge_decision(self,row,*args):
  if row["stock_id"] in ("7711","1809"):return "PASS","test",{"estimated_vr5":3.,"evg_pct":200.}
  return "FAIL","test",{"estimated_vr5":1.,"evg_pct":0.}
 def armed_info(self,d,s):return self.state["volume_armed"].get(d,{}).get(s)
 def arm_volume(self,d,s,reasons,raw,est):return {"reasons":reasons,"estimated_vr5":est,"armed_at":"09:35"}
 def handoff_hit(self,hit,d):
  sym=hit["code"]
  if self.already_sent(d,sym):return False
  if sym in self.failed:raise RuntimeError("injected failure")
  self.sent.append((sym,hit["source"]))
  self.state["discovered"].setdefault(d,{})[sym]=hit
  return True
rows=[{"stock_id":s,"date":day,"name":s,"total_volume":v,"change_rate":3.,"close":103.} for s,v in [("7711",4000),("1809",4000),("2468",4000),("6179",4000)]]
s=Scanner(rows)
capture=io.StringIO()
with contextlib.redirect_stdout(capture):
 first=s.scan_once()
print('FIRST_SCAN_DIAGNOSTICS')
print(capture.getvalue())
print('ARM_STATE',s.state['volume_armed'])
print('EVENTS',logs)
assert s.sent==[("7711","VCP"),("1809","SURGE"),("2468","NO_VCP"),("6179","NO_VCP")],s.sent
assert len(first)==4
with contextlib.redirect_stdout(io.StringIO()):
 second=s.scan_once()
assert not second and len(s.sent)==4,(second,s.sent)
print("PASS actual scan_once method: VCP>SURGE>FLOW dispatch; independent FLOW candidates; same-day no duplicates across two scans")
print("RECEIPTS",s.sent)
print("LIMIT: synthetic snapshots, mocked VCP/F10/selector/bridge, no historical market feed, 5-second cadence, disk, network, or LINE.")
