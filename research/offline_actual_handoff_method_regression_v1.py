#!/usr/bin/env python3
"""Execute the actual candidate Scanner.handoff_hit method in a no-I/O sandbox.
This tests bridge acknowledgement, day dedup, independent route submissions,
and retry after bridge failure. Not a 5-second historical scanner replay.
"""
import ast
import pathlib
import urllib.request
from datetime import datetime

SHA="17ecf3b368ec6b60499194269d5ee68a4c32d141"
URL=f"https://raw.githubusercontent.com/ting78963/stock-alert/{SHA}/fugle_a_scanner_v2_4.py"
source=urllib.request.urlopen(URL,timeout=30).read().decode("utf-8")
tree=ast.parse(source)
scanner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="Scanner")
method=next(n for n in scanner.body if isinstance(n,ast.FunctionDef) and n.name=="handoff_hit")
assert "self.bridge_send(payload)" in ast.get_source_segment(source,method)
assert "self.mark_sent(snap_date, symbol, payload)" in ast.get_source_segment(source,method)
module=ast.Module(body=[ast.FunctionDef(name="handoff_hit",args=method.args,body=method.body,decorator_list=[],returns=None,type_comment=None)],type_ignores=[])
ast.fix_missing_locations(module)
events=[]
class Clock:
 def strftime(self,fmt):return "09:35:00"
namespace={"Dict":dict,"Any":object,"now_tw":lambda:Clock(),"iso_now":lambda:"2026-10-22T09:35:00+08:00","append_event":events.append}
exec(compile(module,URL,"exec"),namespace)
class Sandbox:
 handoff_hit=namespace["handoff_hit"]
 def __init__(self):
  self.state={"discovered":{}};self.receipts=[];self.fail_next=set()
 def already_sent(self,d,s):return s in self.state["discovered"].get(d,{})
 def bridge_send(self,payload):
  if payload["stock_id"] in self.fail_next:
   self.fail_next.remove(payload["stock_id"]);raise RuntimeError("injected bridge failure")
  self.receipts.append(dict(payload))
 def mark_sent(self,d,s,payload):self.state["discovered"].setdefault(d,{})[s]=dict(payload)
def hit(symbol,route):
 return {"code":symbol,"source":route,"name":symbol,"volRatio":2.5,"chgPct":2.5}
day="2026-10-22"
s=Sandbox()
# Same symbol VCP -> SURGE -> FLOW: only first acknowledged route wins.
assert s.handoff_hit(hit("7711","VCP"),day) is True
assert s.handoff_hit(hit("7711","SURGE"),day) is False
assert s.handoff_hit(hit("7711","NO_VCP"),day) is False
assert len(s.receipts)==1 and s.receipts[0]["source"]=="VCP"
# Routes are not in a shared FIFO: different symbols independently succeed.
assert s.handoff_hit(hit("2468","NO_VCP"),day) is True
assert s.handoff_hit(hit("1809","SURGE"),day) is True
assert len(s.receipts)==3
# Failure never marks sent, and another scan may retry.
s.fail_next.add("6277")
try:s.handoff_hit(hit("6277","NO_VCP"),day)
except RuntimeError:pass
else:raise AssertionError("injected bridge failure was swallowed")
assert not s.already_sent(day,"6277")
assert s.handoff_hit(hit("6277","NO_VCP"),day) is True
assert s.already_sent(day,"6277")
# Date-specific dedup.
assert s.handoff_hit(hit("7711","SURGE"),"2026-10-23") is True
assert len(s.receipts)==5
assert len(events)==5
print("PASS actual Scanner.handoff_hit: VCP-first receipt; no same-day duplicate; independent routes; failed bridge retry; next-day eligibility")
print("RECEIPTS",[(p["date"],p["stock_id"],p["source"]) for p in s.receipts])
print("SCOPE: Executes extracted production-candidate handoff_hit method, with in-memory stub bridge/state. No network bridge, LINE, disk state writes, full scan_once, FIFO, or 5-second snapshot replay.")
