"""Offline regression for post-restart reporting; never sends LINE or calls Render."""
import ast
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

SOURCE=pathlib.Path(__file__).with_name("production_worker_v2_shared_ws.py").read_text(encoding="utf-8")
TREE=ast.parse(SOURCE)
NAMES={"_restart_post_boot_check","_restart_line_notice"}
FNS=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
CODE=compile(ast.Module(body=FNS,type_ignores=[]),"<restart-verify>","exec")
TZ=ZoneInfo("Asia/Taipei")
DAY="2026-11-09"

class RestartVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.marker=self.root/"daily_restart"/(DAY+".json")
        self.marker.parent.mkdir()
        self.sent=[]
        base=pathlib.Path
        root=self.root
        class FakePath(type(base())):
            def __new__(cls,value):
                if value=="/var/data/stock-alert":value=str(root)
                return super().__new__(cls,value)
        self.ctx={"Path":FakePath,"json":json,"datetime":dt.datetime,
                  "now_tpe":lambda:dt.datetime(2026,11,9,19,2,tzinfo=TZ),
                  "_atomic_json":lambda p,v:p.write_text(json.dumps(v)),
                  "print":lambda *a,**kw:None,"_RESTART_PROCESS_TOKEN":"new-worker-token"}
        exec(CODE,self.ctx)
        self.ctx["_restart_line_notice"]=lambda *args:self.sent.append(args) or True

    def write(self,status="requested",time="2026-11-09T19:00:00+08:00"):
        self.marker.write_text(json.dumps({"day":DAY,"requested_at":time,"status":status,"process_token":"old-worker-token"}))

    def test_pre_request_marker_survives_immediate_shutdown(self):
        self.write("requested")
        self.ctx["_restart_post_boot_check"]()
        self.assertEqual(len(self.sent),1)
        self.assertEqual(json.loads(self.marker.read_text())["status"],"verified")

    def test_same_process_must_not_report_success(self):
        self.write()
        state=json.loads(self.marker.read_text())
        state["process_token"]="new-worker-token"
        self.marker.write_text(json.dumps(state))
        self.ctx["_restart_post_boot_check"]()
        self.assertEqual(self.sent,[])
        self.assertEqual(json.loads(self.marker.read_text())["status"],"requested")

    def test_accepted_marker(self):
        self.write("accepted")
        self.ctx["_restart_post_boot_check"]()
        self.assertEqual(len(self.sent),1)

    def test_no_duplicate_report(self):
        self.write()
        self.ctx["_restart_post_boot_check"]()
        self.ctx["_restart_post_boot_check"]()
        self.assertEqual(len(self.sent),1)

    def test_no_report_without_restart_intent(self):
        self.write("failed")
        self.ctx["_restart_post_boot_check"]()
        self.assertEqual(self.sent,[])

    def test_no_report_for_old_marker(self):
        self.write(time="2026-11-07T19:00:00+08:00")
        self.ctx["_restart_post_boot_check"]()
        self.assertEqual(self.sent,[])

    def test_failed_line_does_not_mark_verified(self):
        self.write()
        self.ctx["_restart_line_notice"]=lambda *args:False
        self.ctx["_restart_post_boot_check"]()
        self.assertEqual(json.loads(self.marker.read_text())["status"],"requested")

if __name__=="__main__":
    unittest.main()
