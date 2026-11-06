"""Offline regression for daily Render restart guard (no network or production restart)."""
import ast
import datetime
import pathlib
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

SOURCE=pathlib.Path(__file__).with_name("production_worker_v2_shared_ws.py").read_text(encoding="utf-8")
TREE=ast.parse(SOURCE)
FN=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="maybe_restart_after_maintenance")
MODULE=compile(ast.Module(body=[FN],type_ignores=[]),"<daily-restart>","exec")
TPE=ZoneInfo("Asia/Taipei")
DAY="2026-11-06"
class Clock:
    current=datetime.datetime(2026,11,6,19,0,tzinfo=TPE)
    @classmethod
    def now(cls):return cls.current
class RestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.marker=self.root/"daily_restart"/f"{DAY}.json"
        self.request_count=0
        class FakePath(type(pathlib.Path())):
            def __new__(cls, value):
                if value=="/var/data/stock-alert":value=str(self.root)
                return super().__new__(cls,value)
        self.FakePath=FakePath
        self.complete=True
        self.ctx={"now_tpe":Clock.now,"Path":FakePath,"os":__import__("os"),
                  "f15_trajectory_store":None,
                  "_atomic_json":lambda p,x:p.write_text(__import__("json").dumps(x)),
                  "print":lambda *a,**k:None}
        exec(MODULE,self.ctx)
    def call(self,stages={"DAILY_K","F10"},notice="2026-11-06T16:00:00+08:00"):
        with patch.dict("sys.modules",{"f15_trajectory_store":MagicMock(report_and_trajectory_complete=lambda day:self.complete)}),patch.dict("os.environ",{"RENDER_API_KEY":"test-only"},clear=False),patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status=200
            self.ctx["maybe_restart_after_maintenance"](DAY,stages,notice)
            return urlopen.call_count
    def test_before_two_hours(self):self.assertEqual(self.call(notice="2026-11-06T17:30:00+08:00"),0)
    def test_missing_maintenance(self):self.assertEqual(self.call(stages={"DAILY_K"}),0)
    def test_missing_line(self):self.assertEqual(self.call(notice=None),0)
    def test_f15_incomplete(self):
        self.complete=False
        self.assertEqual(self.call(),0)
    def test_outside_window(self):
        Clock.current=datetime.datetime(2026,11,6,23,0,tzinfo=TPE)
        try:self.assertEqual(self.call(),0)
        finally:Clock.current=datetime.datetime(2026,11,6,19,0,tzinfo=TPE)
    def test_once_only(self):
        self.assertEqual(self.call(),1)
        self.assertEqual(self.call(),0)
        self.assertTrue(self.marker.exists())
if __name__=="__main__":unittest.main()
