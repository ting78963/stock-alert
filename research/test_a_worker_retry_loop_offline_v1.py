#!/usr/bin/env python3
"""Execute the REAL worker A restart while-body with injected fake clock/verify/process/sleep.
No network, no worker main(), no production A/B/LINE.
"""
import ast,os,types
from pathlib import Path
source=Path("/tmp/a_worker_loop_stage.py").read_text(encoding="utf-8")
tree=ast.parse(source)
gate=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="a_launch_gate_once")
main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
loop=next(n for n in ast.walk(main) if isinstance(n,ast.While) and isinstance(n.test,ast.Constant) and n.test.value is True)
# Compile exact while-loop body in a sandbox with fake dependencies; never call main.
fn=ast.FunctionDef(name="simulate_worker_loop",args=ast.arguments(posonlyargs=[],args=[],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[]),body=[loop],decorator_list=[])
mod=ast.fix_missing_locations(ast.Module(body=[gate,fn],type_ignores=[]))
events=[]
class StopSimulation(BaseException):pass
class Clock:
    def __init__(self):self.dates=["2026-10-12"]*3+["2026-10-13"]*3
    def __call__(self):
        day=self.dates[min(len([x for x in events if x[0]=="date"]),len(self.dates)-1)]
        events.append(("date",day))
        return types.SimpleNamespace(date=lambda:types.SimpleNamespace(isoformat=lambda:day))
class Process:
    def __init__(self,args,**kw):
        events.append(("spawn",kw["env"]["A_VERIFIED_SNAPSHOT_DAY"],kw["env"]["A_LAST_COMPLETED_SESSION"]))
    def wait(self):
        events.append(("exit",0));return 0
def sleep(seconds):
    events.append(("sleep",seconds))
    if len([x for x in events if x[0]=="sleep"])>=5:raise StopSimulation()
def verify(day):
    events.append(("verify",day))
    if len([x for x in events if x[0]=="verify"])==1:raise RuntimeError("DB lag")
    return "2026-10-08" if day=="2026-10-12" else "2026-10-12"
ns={"os":os,"now_tpe":Clock(),"time":types.SimpleNamespace(sleep=sleep),
    "subprocess":types.SimpleNamespace(Popen=Process),"sys":types.SimpleNamespace(executable="python"),
    "A":"/never-run/real-A.py","BASE":"/tmp","bridge":"fake://local",
    "verify_a_history":verify,"StopSimulation":StopSimulation}
# Inject verify into gate by wrapping original gate with the test-only fake verifier.
exec(compile(mod,"<worker-loop-extracted>","exec"),ns)
real_gate=ns["a_launch_gate_once"]
ns["a_launch_gate_once"]=lambda day:real_gate(day,verify)
try:ns["simulate_worker_loop"]()
except StopSimulation:pass
spawns=[x for x in events if x[0]=="spawn"]
verifies=[x for x in events if x[0]=="verify"]
assert events[0]==("date","2026-10-12")
assert events[1]==("verify","2026-10-12")
assert events[2]==("sleep",60),events[:3]
assert spawns and spawns[0]==("spawn","2026-10-12","2026-10-08"),spawns
assert any(x==("spawn","2026-10-13","2026-10-12") for x in spawns),spawns
assert all(x[1:] in [("2026-10-12","2026-10-08"),("2026-10-13","2026-10-12")] for x in spawns)
assert any(x==("sleep",10) for x in events)
print("PASS: actual worker loop blocked first launch and retried after fake 60s")
print("PASS: recovery started fake A with verified environment")
print("PASS: fake A exit triggered restart with fake 10s delay")
print("PASS: day rollover reverified and restarted fake A with new watermark")
print("FAKE_SPAWNS =",len(spawns),"VERIFY_CALLS =",len(verifies))
print("HTTP = NONE; REAL A/B/LINE = NONE; PRODUCTION WRITES = NONE")
