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
        self.cleanup_marker=self.root/"daily_unknown_cleanup"/f"{DAY}.json"
        self.cleanup_marker.parent.mkdir(parents=True,exist_ok=True)
        self.cleanup_marker.write_text('{"day":"2026-11-06","status":"completed","stats":{"removed":1}}',encoding="utf-8")
        self.request_count=0
        class FakePath(type(pathlib.Path())):
            def __new__(cls, value):
                if value=="/var/data/stock-alert":value=str(self.root)
                return super().__new__(cls,value)
        self.FakePath=FakePath
        self.complete=True
        self.ctx={"now_tpe":Clock.now,"Path":FakePath,"os":__import__("os"),"json":__import__("json"),
                  "f15_trajectory_store":None,
                  "_atomic_json":lambda p,x:p.write_text(__import__("json").dumps(x)),
                  "print":lambda *a,**k:None,"_RESTART_PROCESS_TOKEN":"test-worker-token"}
        exec(MODULE,self.ctx)
    def call(self,stages={"DAILY_K","F10"},notice="2026-11-06T16:00:00+08:00"):
        with patch.dict("sys.modules",{"f15_trajectory_store":MagicMock(report_and_trajectory_complete=lambda day:self.complete)}),patch.dict("os.environ",{"RENDER_API_KEY":"test-only"},clear=False),patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status=200
            self.ctx["maybe_restart_after_maintenance"](DAY,stages,notice)
            return urlopen.call_count
    def test_no_fixed_two_hour_delay(self):self.assertEqual(self.call(notice="2026-11-06T18:59:00+08:00"),1)
    def test_completed_at_1630_can_restart(self):
        Clock.current=datetime.datetime(2026,11,6,16,30,tzinfo=TPE)
        try:
            self.assertEqual(self.call(notice="2026-11-06T16:29:00+08:00"),1)
        finally:
            Clock.current=datetime.datetime(2026,11,6,19,0,tzinfo=TPE)
    def test_market_hours_cannot_restart(self):
        Clock.current=datetime.datetime(2026,11,6,13,30,tzinfo=TPE)
        try:
            self.assertEqual(self.call(),0)
        finally:
            Clock.current=datetime.datetime(2026,11,6,19,0,tzinfo=TPE)
    def test_missing_maintenance(self):self.assertEqual(self.call(stages={"DAILY_K"}),0)
    def test_missing_line(self):self.assertEqual(self.call(notice=None),0)
    def test_f15_incomplete(self):
        self.complete=False
        self.assertEqual(self.call(),0)
    def test_outside_window(self):
        Clock.current=datetime.datetime(2026,11,6,23,0,tzinfo=TPE)
        try:self.assertEqual(self.call(),0)
        finally:Clock.current=datetime.datetime(2026,11,6,19,0,tzinfo=TPE)
    def test_archive_busy(self):
        from daily_restart_coordination import archive_restart_lock
        archive_restart_lock.acquire()
        try:
            self.assertEqual(self.call(),0)
            self.assertFalse(self.marker.exists())
        finally:
            archive_restart_lock.release()
    def test_cleanup_incomplete_blocks_restart(self):
        self.cleanup_marker.unlink()
        self.assertEqual(self.call(),0)
        self.assertFalse(self.marker.exists())
    def test_once_only(self):
        self.assertEqual(self.call(),1)
        self.assertEqual(self.call(),0)
        self.assertTrue(self.marker.exists())
if __name__=="__main__":unittest.main()
