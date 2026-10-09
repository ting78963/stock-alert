#!/usr/bin/env python3
"""Isolated sequential maintenance test: 15:30 gate, daily->F10, failure blocks F10."""
import ast,datetime as dt,os,sys
from pathlib import Path
from unittest.mock import patch
src=Path("/tmp/worker_1530_staging.py")
if not src.exists():raise SystemExit("STOP missing /tmp/worker_1530_staging.py")
tree=ast.parse(src.read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="daily_history_maintenance_loop")
class Stop(Exception):pass
class FakePath:
 def __truediv__(self,other):return self
 def is_file(self):return True
def check(name,hour,minute,rcs,expected):
 calls=[]
 class Time:
  @staticmethod
  def monotonic():return 0.
  @staticmethod
  def sleep(sec):raise Stop()
 def call(cmd,**kwargs):
  calls.append("DAILY_K" if "--execute" in cmd else "F10")
  return rcs[len(calls)-1]
 ns={"os":os,"BASE":FakePath(),"now_tpe":lambda:dt.datetime(2026,10,9,hour,minute),
 "is_scheduled_open":lambda d:True,"time":Time,"sys":sys,"print":lambda *a,**kw:None}
 exec(compile(ast.Module(body=[fn],type_ignores=[]),str(src),"exec"),ns)
 with patch.dict(os.environ,{"A_DAILY_HISTORY_MAINTENANCE_ENABLED":"1"}),patch("subprocess.call",side_effect=call):
  try:ns["daily_history_maintenance_loop"]()
  except Stop:pass
 assert calls==expected,(name,calls,expected)
 print("PASS",name,"->",",".join(calls) or "NO CALLS")
check("15:29 no update",15,29,[] ,[])
check("15:30 sequential success",15,30,[0,0],["DAILY_K","F10"])
check("daily K failure blocks F10",15,30,[1],["DAILY_K"])
check("F10 failure after daily success",15,30,[0,1],["DAILY_K","F10"])
print("RESULT = PASS | NO HTTP/DB/LINE/Worker launch")
