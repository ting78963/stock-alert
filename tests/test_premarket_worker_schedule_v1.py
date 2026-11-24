"""Exercise the actual worker loop without starting other production threads."""
import ast
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

class StopLoop(BaseException): pass

class ScheduleTests(unittest.TestCase):
    def simulate(self, opened=True, fail=False):
        tree=ast.parse(Path("production_worker_v1.py").read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="premarket_sox_loop")
        # Redirect the persistent marker to a nonexistent temporary location.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for n in ast.walk(fn):
                if isinstance(n,ast.Constant) and n.value=="/var/data/stock-alert/market_data/premarket_sox_sent.json":
                    n.value=tmp+"/sent.json"
            current=datetime(2026,11,24,8,53,55,tzinfo=ZoneInfo("Asia/Taipei"))
            calls=[]
            class Clock:
                @staticmethod
                def now(tz): return current
            def sleep(seconds):
                nonlocal current
                current+=timedelta(seconds=seconds)
                if current.hour>=9 and current.minute>=1: raise StopLoop()
            def build(*args,**kwargs):
                calls.append(("build",current))
                return {"type":"flex"}
            def deliver(*args,**kwargs):
                calls.append(("send",current))
                if fail: raise OSError("simulated")
                return "sent"
            mods={
                "research.premarket_sox_delivery_v1":SimpleNamespace(deliver_premarket_once=deliver),
                "research.premarket_sox_sender_v1":SimpleNamespace(send_premarket_flex=lambda _:True),
                "research.premarket_market_brief_v1":SimpleNamespace(build_market_brief=build),
                "twse_session_gate_v1":SimpleNamespace(is_scheduled_open=lambda _:opened)}
            env={"datetime":Clock,"ZoneInfo":ZoneInfo,"time":SimpleNamespace(sleep=sleep)}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),"<worker>","exec"),env)
            with patch.dict(sys.modules,mods),self.assertRaises(StopLoop):
                env["premarket_sox_loop"]()
            return calls
    def test_normal(self):
        calls=self.simulate()
        self.assertEqual([(k,t.hour,t.minute) for k,t in calls],[("build",8,54),("send",8,55)])
    def test_closed(self):
        self.assertEqual(self.simulate(opened=False),[])
    def test_retry_cutoff(self):
        calls=self.simulate(fail=True)
        sends=[t for k,t in calls if k=="send"]
        self.assertGreater(len(sends),1)
        self.assertTrue(all(t.hour==8 and t.minute>=55 for t in sends))
        self.assertTrue(all((b-a).total_seconds()>=20 for a,b in zip(sends,sends[1:])))
        self.assertEqual(sum(k=="build" for k,t in calls),1)
