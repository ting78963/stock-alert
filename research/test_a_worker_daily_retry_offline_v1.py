#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline test: failed maintenance retries after 30 min; success stops same-day retries."""
import ast,datetime as dt,os,sys
from pathlib import Path
from unittest.mock import patch
p=Path("/tmp/worker_daily_staging.py")
if not p.is_file():raise SystemExit("STOP: staging worker missing in /tmp")
node=next(n for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="daily_history_maintenance_loop")
class End(Exception):pass
class FakePath:
    def __truediv__(self,other):return self
    def is_file(self):return True
tz=dt.timezone(dt.timedelta(hours=8))
clock=[0.0];attempts=[];loops=[0]
def fake_sleep(sec):
    loops[0]+=1
    if loops[0]>65:raise End()
    clock[0]+=60
def fake_call(cmd,**kwargs):
    attempts.append(clock[0])
    return 2 if len(attempts)==1 else 0
ns={"os":os,"BASE":FakePath(),"now_tpe":lambda:dt.datetime(2026,10,9,14,31,tzinfo=tz),
    "is_scheduled_open":lambda day:True,"time":type("Time",(),{"sleep":fake_sleep,"monotonic":lambda:clock[0]}),
    "sys":sys,"print":lambda *args,**kwargs:None}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),"exec"),ns)
with patch.dict(os.environ,{"A_DAILY_HISTORY_MAINTENANCE_ENABLED":"1"}),patch("subprocess.call",side_effect=fake_call):
    try:ns["daily_history_maintenance_loop"]()
    except End:pass
assert attempts==[0.0,1800.0],attempts
print("PASS first failure at t=0; retry at t=1800 seconds")
print("PASS success stops further same-day attempts")
print("RESULT = PASS | mocked subprocess/calendar/time | NO HTTP/DB/LINE/Worker launch")
