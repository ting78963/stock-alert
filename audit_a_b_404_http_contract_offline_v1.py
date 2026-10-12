#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A->B HTTP response contract replay, offline and without importing production modules."""
import ast, io, json, pathlib, types, urllib.request
from unittest.mock import patch
root=pathlib.Path(__file__).resolve().parent
src=(root/"fugle_a_scanner_v2_4.py").read_text(encoding="utf-8")
tree=ast.parse(src)
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and any(isinstance(m,ast.FunctionDef) and m.name=="bridge_send" for m in n.body))
methods=[m for m in cls.body if isinstance(m,ast.FunctionDef) and m.name in {"bridge_send","handoff_hit","already_sent","mark_sent"}]
assert len(methods)==4
c=ast.ClassDef(name="ScannerUnderTest",bases=[],keywords=[],body=methods,decorator_list=[])
mod=ast.fix_missing_locations(ast.Module(body=[c],type_ignores=[]))
events=[]
def save_json_atomic(*args):pass
def append_event(event):events.append(event)
env={"json":json,"urllib":__import__("urllib"),"Optional":__import__("typing").Optional,"Dict":__import__("typing").Dict,"Any":__import__("typing").Any,
     "STATE_FILE":root/"not_written.json","save_json_atomic":save_json_atomic,"append_event":append_event,
     "now_tw":lambda:types.SimpleNamespace(strftime=lambda fmt:"09:30:00"),"iso_now":lambda:"2026-10-12T09:30:00"}
exec(compile(mod,"<isolated-A-methods>","exec"),env)
scanner=env["ScannerUnderTest"]()
scanner.bridge_url="http://127.0.0.1:8765/discovery"
scanner.state={"discovered":{}}
hit={"code":"2323","source":"A","name":"中環","volRatio":1.7,"chgPct":4.0}
class Response:
    status=200
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self):return json.dumps(self.data).encode()
def request(data):
    return patch.object(urllib.request,"urlopen",return_value=Response(data))
with request({"ok":True,"skipped":True,"reason":"individual_history_404","launched":False}):
    assert scanner.handoff_hit(hit,"2026-10-12") is False
assert scanner.state["discovered"]["2026-10-12"]["2323"]["handoff_status"]=="history_404_skipped"
assert events[-1]["type"]=="b_history_404_skipped"
print("[PASS] A HTTP 200 skip: persisted skipped status, no success discovery")
with patch.object(urllib.request,"urlopen",side_effect=AssertionError("must not call HTTP again")):
    assert scanner.handoff_hit(hit,"2026-10-12") is False
print("[PASS] A same-day rediscovery: no additional bridge HTTP")
hit2=dict(hit,code="2324",name="仁寶")
with request({"ok":True,"launched":True}):
    assert scanner.handoff_hit(hit2,"2026-10-12") is True
assert events[-1]["type"]=="discovery"
print("[PASS] A normal 2324 response: successful discovery")
hit3=dict(hit,code="2330",name="台積電")
with request({"ok":True,"skipped":True,"reason":"unknown"}):
    try:scanner.handoff_hit(hit3,"2026-10-12")
    except RuntimeError:pass
    else:raise AssertionError("unknown skip must fail")
assert not scanner.already_sent("2026-10-12","2330")
print("[PASS] unknown skip reason fails closed without dedupe")
print("OFFLINE A HTTP CONTRACT PASS | MOCK HTTP | NO NETWORK | NO PRODUCTION WRITE")
