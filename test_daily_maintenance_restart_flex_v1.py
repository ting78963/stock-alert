import ast
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parent
SOURCE=(ROOT/"production_worker_v2_shared_ws.py").read_text(encoding="utf-8")

class DailyRestartReportRegression(unittest.TestCase):
    def test_source_compiles(self):
        ast.parse(SOURCE)

    def test_restart_uses_flex_and_blue_header(self):
        tree=ast.parse(SOURCE)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_restart_line_notice")
        src=ast.get_source_segment(SOURCE,fn)
        self.assertIn('"type":"flex"',src)
        self.assertIn('"#193B63"',src)
        self.assertNotIn('"type":"text","text":message',src)

    def test_maintenance_report_persists_and_restores(self):
        tree=ast.parse(SOURCE)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="daily_history_maintenance_loop")
        src=ast.get_source_segment(SOURCE,fn)
        self.assertIn('daily_maintenance_state',src)
        self.assertIn('persisted.get("report_sent") is True',src)
        self.assertIn('"report_sent":True',src)
        self.assertIn('completed_day=day',src)
        self.assertIn('_atomic_json(state_dir/f"{day}.json"',src)

if __name__=="__main__":
    unittest.main()
