#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline integration test of actual Worker daily maintenance loop; no production actions."""
import ast
import datetime as dt
import os
from pathlib import Path
from unittest.mock import patch

SRC=Path("/tmp/worker_daily_staging.py")
if not SRC.is_file():raise SystemExit("STOP: download staging worker to /tmp first")
tree=ast.parse(SRC.read_text(encoding="utf-8"))
node=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="daily_history_maintenance_loop"),None)
if node is None:raise SystemExit("STOP: maintenance loop missing")
class StopLoop(Exception):pass
tz=dt.timezone(dt.timedelta(hours=8))
class FakePath:
    def __truediv__(self,other):return self
    def is_file(self):return True
def run(label,hour,minute,enabled,open_day,expected):
    events=[]
    fake_now=dt.datetime(2026,10,9,hour,minute,tzinfo=tz)
    def call(cmd,**kwargs):
        events.append(("call",tuple(cmd)))
        return 0
    def sleep(seconds):raise StopLoop()
    ns={"os":os,"BASE":FakePath(),"now_tpe":lambda:fake_now,
        "is_scheduled_open":lambda day:open_day,"time":type("Time",(),{"sleep":sleep}),
        "sys":__import__("sys"),"print":lambda *args,**kwargs:None}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(SRC),"exec"),ns)
    with patch.dict(os.environ,{"A_DAILY_HISTORY_MAINTENANCE_ENABLED":"1" if enabled else "0"}),patch("subprocess.call",side_effect=call):
        try:ns["daily_history_maintenance_loop"]()
        except StopLoop:pass
    count=len(events)
    assert count==expected,(label,events)
    print(f"PASS {label}: maintenance_calls={count}")
run("default disabled",14,31,False,True,0)
run("enabled before close",14,29,True,True,0)
run("enabled closed session",14,31,True,False,0)
run("enabled open session after close",14,31,True,True,1)
print("RESULT = PASS | actual Worker function, mocked subprocess/time/calendar | NO HTTP/DB/LINE/Worker launch")
