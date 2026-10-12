#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline B 404 lifecycle replay; isolated AST functions, fake runner, temp state."""
import ast, json, pathlib, re, tempfile, threading, types
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parent
source=(ROOT/"production_worker_v2_shared_ws.py").read_text(encoding="utf-8")
tree=ast.parse(source)
names={"_atomic_json","_history404_path","_history404_load","_history404_has","_history404_mark","_is_individual_history404","key","launch_b"}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
assert {n.name for n in nodes}==names
mod=ast.Module(body=nodes,type_ignores=[])
ast.fix_missing_locations(mod)
with tempfile.TemporaryDirectory(prefix="b404_replay_") as tmp:
    state=pathlib.Path(tmp)
    env={"STATE_ROOT":state,"_lock":threading.RLock(),"_f14_done":set(),"_runners":{},"_launching":set(),"_queues":{},"LINE_SEND":False,
         "json":json,"re":re,"queue":__import__("queue"),"threading":threading,"BASE":ROOT}
    def f14_ensure_day(day):pass
    env["f14_ensure_day"]=f14_ensure_day
    calls=[]
    class FakeRunner:
        def __init__(self,sid,day,disc,minutes,**kw):
            calls.append((day,sid))
            if sid=="2323" and day=="2026-10-12":
                raise SystemExit("AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL | Fugle HTTP 404 | daily-calendar 2323 2026-10-12")
            if sid=="2330" and day=="2026-10-12":
                raise SystemExit("Fugle HTTP 429 | daily-calendar 2330 2026-10-12")
            self.retired=False
        def rest_reconcile(self,reason):pass
    env.update(runner_module=lambda:{"Runner":FakeRunner},worker_loop=lambda *args:None,subscribe_symbol=lambda sid:None)
    # Prevent starting worker threads; only validate B initialization and response semantics.
    class FakeThread:
        def __init__(self,*args,**kw):pass
        def start(self):pass
    env["threading"]=types.SimpleNamespace(Thread=FakeThread)
    exec(compile(mod,str(ROOT/"production_worker_v2_shared_ws.py"),"exec"),env)
    launch=env["launch_b"]
    def payload(sid,day="2026-10-12"):
        return {"stock_id":sid,"date":day,"discovered_at":"09:30:00"}
    first=launch(payload("2323"))
    assert first["skipped"] and not first["launched"] and calls==[("2026-10-12","2323")]
    assert env["_history404_path"]("2026-10-12").is_file()
    print("[PASS] 2323 first historical 404: one attempted runner, persisted skip")
    for _ in range(100):
        assert launch(payload("2323"))["skipped"]
    assert len(calls)==1
    print("[PASS] same-day 100 rediscoveries: zero additional runner/API initializations")
    # Simulate process restart by loading fresh isolated function namespace.
    env2=dict(env)
    env2.update(_lock=threading.RLock(),_runners={},_launching=set(),_queues={})
    exec(compile(mod,str(ROOT/"production_worker_v2_shared_ws.py"),"exec"),env2)
    assert env2["launch_b"](payload("2323"))["skipped"] and len(calls)==1
    print("[PASS] restart restores skip from persistent JSON")
    good=env2["launch_b"](payload("2324"))
    assert good["launched"] and not good.get("skipped") and len(calls)==2
    print("[PASS] unrelated 2324 still launches B")
    try:env2["launch_b"](payload("2330"))
    except SystemExit:pass
    else:raise AssertionError("429 must fail closed")
    assert not env2["_history404_has"]("2026-10-12","2330")
    print("[PASS] HTTP 429 not quarantined")
    nextday=env2["launch_b"](payload("2323","2026-10-13"))
    assert nextday["launched"] and calls[-1]==("2026-10-13","2323")
    print("[PASS] next day 2323 can launch B again")
print("OFFLINE B RUNTIME REPLAY PASS | FAKE RUNNER | NO NETWORK | NO PRODUCTION WRITE")
