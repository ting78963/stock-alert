"""Offline B 13:31 retirement smoke tests. No production imports, network, LINE or writes."""
import ast
from pathlib import Path
src=Path(__file__).resolve().parents[2]/"production_worker_v2_shared_ws.py"
tree=ast.parse(src.read_text(encoding="utf-8"))
fns={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
for name in ("b_time_expired","retire_runner","worker_loop","clock_loop","launch_b"):
    assert name in fns,name
scope={}
exec(compile(ast.Module(body=[fns["b_time_expired"]],type_ignores=[]),str(src),"exec"),{"now_tpe":lambda:None},scope)
from datetime import datetime
expired=scope["b_time_expired"]
for hh,mm,want in [(9,0,False),(13,30,False),(13,31,True),(15,0,True)]:
    assert expired(datetime(2026,10,15,hh,mm)) is want,(hh,mm)
clock=ast.unparse(fns["clock_loop"])
assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='retire_runner' and any(kw.arg=='reason' and isinstance(kw.value,ast.Constant) and kw.value.value=='13:31' for kw in n.keywords) for n in ast.walk(fns['clock_loop']))
assert 'b_time_expired()' in ast.unparse(fns["worker_loop"])
assert 'b_time_expired()' in ast.unparse(fns["launch_b"])
assert 'f14_mark_done' not in ast.unparse(fns["retire_runner"])
assert 'f14_mark_done(k)' in ast.unparse(fns["launch_b"])
assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='retire_runner' for n in ast.walk(fns['launch_b']))
print("[PASS] 13:30 still active; 13:31 closed")
print("[PASS] B clock uses existing retire_runner")
print("[PASS] worker and admission time guard")
print("[PASS] timeout does not mark LINE sent; successful LINE retains F14")
print("[PASS] Python source parses")
print("NOTE: Static/isolated smoke only; not a live-thread or production test")
