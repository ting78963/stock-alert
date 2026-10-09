#!/usr/bin/env python3
"""Offline read-only source call-path audit for staged A."""
import ast
from pathlib import Path
s=Path("/tmp/a_paths_stage.py").read_text(encoding="utf-8")
t=ast.parse(s)
classes={n.name:n for n in t.body if isinstance(n,ast.ClassDef)}
for cname in ("Scanner","FugleAdapter","WaitDataWorker"):
    assert cname in classes,cname
def methods(c):
    return {n.name:n for n in classes[c].body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
def calls(fn):
    return sorted(set(ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n,ast.Call)))
sc=methods("Scanner");ad=methods("FugleAdapter");wk=methods("WaitDataWorker")
scan=calls(sc["scan_once"])
print("SCAN_ONCE adapter daily calls:",[x for x in scan if "daily_history" in x])
print("SCAN_ONCE ticker calls:",[x for x in scan if "ticker" in x])
print("SCAN_ONCE WAIT_DATA calls:",[x for x in scan if "wait_data_worker" in x])
assert "self.adapter.daily_history_local_ready" in scan
assert "self.wait_data_worker.submit" in scan
assert "self.adapter.daily_history" not in scan
print("PASS: scan_once uses local-ready history and background queue, not direct daily_history")
for name in ("daily_history_local_ready","daily_history","ticker"):
    print("ADAPTER",name,"network calls:",[x for x in calls(ad[name]) if "http_json" in x or "historical_json" in x])
assert "self.historical_json" in calls(ad["daily_history"])
assert "http_json" in calls(ad["ticker"])
print("RISK: separate direct history method remains callable outside scan_once")
print("RISK: ticker cache MISS uses direct HTTP, outside history 429 worker")
print("STATIC_SOURCE_AUDIT_ONLY; HTTP=NONE; A/B/LINE=NONE; PRODUCTION_WRITES=NONE")
