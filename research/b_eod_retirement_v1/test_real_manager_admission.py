# -*- coding: utf-8 -*-
"""AST-only integration checks for the real shared-WS B manager. No imports/side effects."""
import ast
import datetime
import pathlib
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "production_worker_v2_shared_ws.py"

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {n.name:n for n in cls.tree.body if isinstance(n,ast.FunctionDef)}

    def test_actual_manager_source(self):
        self.assertIn("launch_b", self.functions)
        self.assertIn("worker_loop", self.functions)
        self.assertIn("b_session_admission", self.functions)

    def test_gate_boundaries(self):
        f = self.functions["b_session_admission"]
        ns = {"now_tpe":lambda:None}
        exec(compile(ast.Module(body=[f],type_ignores=[]),str(SOURCE),"exec"),ns)
        fn = ns["b_session_admission"]
        def at(hour,minute,day=15):
            return datetime.datetime(2026,10,day,hour,minute)
        self.assertFalse(fn("2026-10-15",at(8,59)))
        self.assertTrue(fn("2026-10-15",at(9,0)))
        self.assertTrue(fn("2026-10-15",at(13,29)))
        self.assertFalse(fn("2026-10-15",at(13,30)))
        self.assertFalse(fn("2026-10-15",at(13,31)))
        self.assertFalse(fn("2026-10-15",at(9,30,16)))

    def test_both_claim_and_publish_gate(self):
        node = self.functions["launch_b"]
        calls = [n for n in ast.walk(node) if isinstance(n,ast.Call)
                 and isinstance(n.func,ast.Name) and n.func.id=="b_session_admission"]
        self.assertEqual(len(calls),2)

    def test_self_test_dry_run_not_blocked(self):
        node = self.functions["launch_b"]
        self.assertIn("not dry_run and not b_session_admission(day)",ast.unparse(node))

if __name__=="__main__":
    print("RESEARCH ONLY | AST TEST | NO PRODUCTION IMPORT | NO API | NO LINE")
    unittest.main(verbosity=2)
