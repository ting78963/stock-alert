#!/usr/bin/env python3
"""Actual B launch_b + actual A handoff_hit, in-memory end-to-end ACK regression.
No server, sockets, LINE, production files, threads, or external B API.
"""
import ast,urllib.request,threading,queue
BASE="https://raw.githubusercontent.com/ting78963/stock-alert/"
def extract(sha,path,clsname,fnname):
 url=BASE+sha+"/"+path
 source=urllib.request.urlopen(url,timeout=30).read().decode()
 tree=ast.parse(source)
 nodes=tree.body if clsname is None else next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==clsname).body
 f=next(n for n in nodes if isinstance(n,ast.FunctionDef) and n.name==fnname)
 m=ast.Module(body=[ast.FunctionDef(name=fnname,args=f.args,body=f.body,decorator_list=[],returns=None,type_comment=None)],type_ignores=[])
 ast.fix_missing_locations(m)
 return compile(m,url,"exec")
events=[];state={"discovered":{}}
lock=threading.RLock();runners={};queues={};launching=set();done=set();starts=[];subscriptions=[];fail=False
class FakeRunner:
 def __init__(self,*args,**kwargs):self.retired=False
 def rest_reconcile(self,reason):pass
def runner_module():
 if fail:raise RuntimeError("B launch injected failure")
 return {"Runner":FakeRunner}
def key(day,sid):return str(day)+"|"+str(sid).zfill(4)
def worker_loop(*args):raise AssertionError("should not start a real worker")
class FakeThread:
 def __init__(self,target,args,daemon):assert target is worker_loop;self.args=args
 def start(self):starts.append(self.args[0])
class FakeThreading:
 Thread=FakeThread
bns={"_lock":lock,"_runners":runners,"_queues":queues,"_launching":launching,"_f14_done":done,
 "f14_ensure_day":lambda day:None,"b_time_expired":lambda:False,"key":key,
 "runner_module":runner_module,"LINE_SEND":False,"queue":queue,"threading":FakeThreading,
 "worker_loop":worker_loop,"subscribe_symbol":subscriptions.append}
exec(extract("7a92b891bf017b6ca73d90a38648fb8647673795","production_worker_v2_shared_ws.py",None,"launch_b"),bns)
from datetime import datetime
ans={"Dict":dict,"Any":object,"now_tw":lambda:datetime.fromisoformat("2026-10-22T09:35:00+08:00"),
 "iso_now":lambda:"2026-10-22T09:35:00+08:00","append_event":events.append}
exec(extract("6a4b969e8f32f0a65c5e12075d6015b82a33b86b","fugle_a_scanner_v2_4.py","Scanner","handoff_hit"),ans)
class A:
 handoff_hit=ans["handoff_hit"]
 layered_a_enabled=True
 def __init__(self):self.state={"discovered":{}};self.fail_transport=False
 def already_sent(self,d,s):return s in self.state["discovered"].get(d,{})
 def mark_sent(self,d,s,p):self.state["discovered"].setdefault(d,{})[s]=p
 def bridge_send(self,p):
  response=bns["launch_b"](p)
  if self.fail_transport:raise RuntimeError("HTTP response lost after B accepted")
  return {"http_status":200,"body":response}
def hit(s):return {"code":s,"source":"VCP","name":s,"volRatio":2.5,"chgPct":3.0}
day="2026-10-22";a=A()
assert a.handoff_hit(hit("7711"),day) is True
assert len(starts)==1 and len(subscriptions)==1
assert a.handoff_hit(hit("7711"),day) is False and len(starts)==1
print("PASS actual A->B launch: one B runner, A dedupe")
# Another A instance has no discovery state; B must report duplicate without a second runner.
a2=A();assert a2.handoff_hit(hit("7711"),day) is True and len(starts)==1
print("PASS B duplicate ACK: no second runner")
# Simulate successful B launch but lost HTTP response; retry should be deduped by B.
a3=A();a3.fail_transport=True
try:a3.handoff_hit(hit("2468"),day)
except RuntimeError:pass
else:raise AssertionError("lost ACK must fail")
assert not a3.already_sent(day,"2468") and len(starts)==2
a3.fail_transport=False
assert a3.handoff_hit(hit("2468"),day) is True and len(starts)==2
print("PASS lost ACK after launch: retry accepted, no duplicate B runner")
# B launch fails before acceptance: A keeps retryable.
global_fail=False
fail=True
a4=A()
try:a4.handoff_hit(hit("6179"),day)
except RuntimeError:pass
else:raise AssertionError("B launch failure must propagate")
assert not a4.already_sent(day,"6179") and len(starts)==2
fail=False
assert a4.handoff_hit(hit("6179"),day) is True and len(starts)==3
print("PASS B launch exception: A retries successfully")
done.add(key(day,"9933"))
a5=A();assert a5.handoff_hit(hit("9933"),day) is True and len(starts)==3
print("PASS B F14 already done: acknowledged, no runner")
print("SUMMARY PASS actual A handoff_hit + actual B launch_b, stubbed Runner/threads/WS/state; no HTTP server, network bridge, LINE, disk writes, full scan")
