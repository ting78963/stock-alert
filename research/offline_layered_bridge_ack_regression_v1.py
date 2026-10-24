#!/usr/bin/env python3
"""No-network regression of actual candidate Scanner.handoff_hit ACK policy.
No production state, Bridge requests or LINE messages.
"""
import ast,urllib.request
from datetime import datetime
SHA="6a4b969e8f32f0a65c5e12075d6015b82a33b86b"
URL=f"https://raw.githubusercontent.com/ting78963/stock-alert/{SHA}/fugle_a_scanner_v2_4.py"
src=urllib.request.urlopen(URL,timeout=30).read().decode("utf-8")
tree=ast.parse(src)
cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=="Scanner")
fn=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=="handoff_hit")
mod=ast.Module(body=[ast.FunctionDef(name="handoff_hit",args=fn.args,body=fn.body,decorator_list=[],returns=None,type_comment=None)],type_ignores=[])
ast.fix_missing_locations(mod)
events=[]
ns={"Dict":dict,"Any":object,"now_tw":lambda:datetime.fromisoformat("2026-10-22T09:35:00+08:00"),"iso_now":lambda:"2026-10-22T09:35:00+08:00","append_event":events.append}
exec(compile(mod,URL,"exec"),ns)
DAY="2026-10-22";KEY=DAY+"|7711"
def hit():return {"code":"7711","source":"VCP","name":"7711","volRatio":2.5,"chgPct":3}
class Sandbox:
 handoff_hit=ns["handoff_hit"]
 def __init__(self,layered=True):
  self.layered_a_enabled=layered;self.state={"discovered":{}};self.ack=None;self.calls=0
 def already_sent(self,d,s):return s in self.state["discovered"].get(d,{})
 def bridge_send(self,p):
  self.calls+=1
  if isinstance(self.ack,Exception):raise self.ack
  return self.ack
 def mark_sent(self,d,s,p):self.state["discovered"].setdefault(d,{})[s]=p
def run(label,ack,success=False,layered=True):
 s=Sandbox(layered);s.ack=ack
 try:result=s.handoff_hit(hit(),DAY);err=None
 except RuntimeError as e:result=False;err=str(e)
 assert (result is True)==success,(label,result,err)
 assert s.already_sent(DAY,"7711")==success,(label,"state")
 assert len(events)==run.event_count+int(success),(label,"events")
 print("PASS",label,"accepted" if success else "retryable",err or "")
 if success:
  assert s.handoff_hit(hit(),DAY) is False and s.calls==1
  print("PASS",label,"same-day dedupe")
run.event_count=0
cases=[
 ("missing_bridge",None,False,True),
 ("transport_failure",RuntimeError("timeout"),False,True),
 ("http_500",{"http_status":500,"body":{"ok":True,"key":KEY,"launched":True}},False,True),
 ("http_200_invalid_json",{"http_status":200,"body":None},False,True),
 ("http_200_rejected",{"http_status":200,"body":{"ok":False,"key":KEY,"launched":True}},False,True),
 ("http_200_wrong_key",{"http_status":200,"body":{"ok":True,"key":DAY+"|2468","launched":True}},False,True),
 ("http_200_no_acceptance",{"http_status":200,"body":{"ok":True,"key":KEY,"launched":False}},False,True),
 ("b_launched",{"http_status":200,"body":{"ok":True,"key":KEY,"launched":True}},True,True),
 ("b_duplicate",{"http_status":200,"body":{"ok":True,"key":KEY,"duplicate":True,"launched":False}},True,True),
 ("b_already_done",{"http_status":200,"body":{"ok":True,"key":KEY,"already_done":True,"launched":False}},True,True),
 ("legacy_dry_unchanged",None,True,False),
]
for label,ack,ok,layered in cases:
 run.event_count=len(events);run(label,ack,ok,layered)
print("SUMMARY",len(cases),"ACK cases passed; actual candidate handoff_hit; no B launch, LINE, network bridge or disk mutation")
