#!/usr/bin/env python3
"""Offline real child-process launch gate simulation; never start production A/B/LINE."""
import ast,os,sys,subprocess,tempfile
from pathlib import Path
src=Path("/tmp/a_worker_process_stage.py").read_text(encoding="utf-8")
tree=ast.parse(src)
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="a_launch_gate_once")
ns={"os":os}
exec(compile(ast.Module(body=[node],type_ignores=[]),"<extracted-worker-gate>","exec"),ns)
gate=ns["a_launch_gate_once"]
calls=[]
def verify(day):
    calls.append(day)
    if len(calls)==1:raise RuntimeError("simulated DB lag")
    return "2026-10-08"
# Blocked path: no subprocess can be started before gate returns.
try:gate("2026-10-12",verify)
except RuntimeError:print("PASS: DB lag blocks A launch")
else:raise AssertionError("gate should block")
env=gate("2026-10-12",verify)
assert calls==["2026-10-12","2026-10-12"]
assert env["A_LAST_COMPLETED_SESSION"]=="2026-10-08"
assert env["A_VERIFIED_SNAPSHOT_DAY"]=="2026-10-12"
# Actually launch a harmless Python child, NOT the production scanner.
with tempfile.TemporaryDirectory() as td:
    marker=Path(td)/"child.txt"
    child="import os,pathlib,sys;pathlib.Path(sys.argv[1]).write_text(os.environ['A_LAST_COMPLETED_SESSION']+'|'+os.environ['A_VERIFIED_SNAPSHOT_DAY'])"
    result=subprocess.run([sys.executable,"-c",child,str(marker)],env=env,timeout=5,check=True)
    assert marker.read_text()=="2026-10-08|2026-10-12"
print("PASS: recovery allows harmless child process with correct session env")
# Cross-day: new launch requires a fresh verifier call.
def next_day(day):
    assert day=="2026-10-13"
    return "2026-10-12"
env2=gate("2026-10-13",next_day)
assert env2["A_LAST_COMPLETED_SESSION"]=="2026-10-12"
print("PASS: next-day launch receives fresh watermark")
for invalid in ("", "2026-10-13", "2026-10-14"):
    try:gate("2026-10-13",lambda day:invalid)
    except RuntimeError:pass
    else:raise AssertionError("invalid watermark accepted")
print("PASS: invalid preflight return blocks launch")
print("LIMITATION: worker while/retry sleep not exercised; no real A or B process launched")
print("NETWORK = NONE; PRODUCTION_WRITES = NONE")
