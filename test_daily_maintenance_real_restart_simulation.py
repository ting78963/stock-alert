"""No-network restart regression for the actual production maintenance loop."""
import ast
import datetime as dt
import json
import os
import pathlib
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parent
SOURCE=(ROOT/"production_worker_v2_shared_ws.py").read_text(encoding="utf-8")

class StopLoop(Exception):
    pass

class RestartSimulation(unittest.TestCase):
    def test_restart_skips_completed_maintenance_and_line(self):
        tree=ast.parse(SOURCE)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="daily_history_maintenance_loop")
        # Execute the real function body; redirect only the persistent directory
        # to an isolated temp folder, without touching production /var/data.
        with tempfile.TemporaryDirectory() as td:
            state_dir=pathlib.Path(td)/"daily_maintenance_state"
            state_dir.mkdir()
            day="2026-11-09"
            (state_dir/(day+".json")).write_text(json.dumps({
                "day":day,"stage_done":["DAILY_K","F10"],
                "report_sent":True,"notified_at":"2026-11-09T22:04:36+08:00"
            }),encoding="utf-8")
            assign=next(n for n in ast.walk(fn) if isinstance(n,ast.Assign) and
                any(isinstance(t,ast.Name) and t.id=="state_dir" for t in n.targets))
            assign.value=ast.Constant(value=str(state_dir))
            ast.fix_missing_locations(fn)
            module=ast.Module(body=[fn],type_ignores=[])
            ast.fix_missing_locations(module)
            calls=[]
            class FakeTime:
                @staticmethod
                def monotonic(): return 0.0
                @staticmethod
                def sleep(_): raise StopLoop()
            fake_subprocess=types.SimpleNamespace(call=lambda *a,**k:calls.append("maintenance"))
            import sys
            real_import=__import__
            def guarded_import(name,*args,**kwargs):
                if name=="subprocess": return fake_subprocess
                return real_import(name,*args,**kwargs)
            env={"os":os,"Path":pathlib.Path,"json":json,"time":FakeTime,
                 "now_tpe":lambda:dt.datetime(2026,11,9,22,24,tzinfo=dt.timezone(dt.timedelta(hours=8))),
                 "BASE":ROOT,"sys":sys,
                 "is_scheduled_open":lambda _:True,
                 "maybe_restart_after_maintenance":lambda *args:None}
            exec(compile(module,"production_worker_v2_shared_ws.py","exec"),env)
            with patch.dict(os.environ,{"A_DAILY_HISTORY_MAINTENANCE_ENABLED":"1","A_DAILY_MAINT_LINE_REPORT":"1"}),patch("builtins.__import__",side_effect=guarded_import):
                for _ in range(2):  # Two independent process boots, same disk
                    with self.assertRaises(StopLoop):
                        env["daily_history_maintenance_loop"]()
            self.assertEqual(calls,[],"Restart must not rerun DAILY_K or F10")
            self.assertTrue(json.loads((state_dir/(day+".json")).read_text())["report_sent"])

if __name__=="__main__":
    unittest.main()
