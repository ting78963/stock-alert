"""Regression: optional indicator timeout must not alter existing Fugle callers."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).parent

class FugleIndicatorTimeoutTests(unittest.TestCase):
    def test_optional_timeout_preserves_default(self):
        tree=ast.parse((ROOT/"fugle_adapter.py").read_text(encoding="utf-8"))
        funcs={x.name:x for x in tree.body if isinstance(x,ast.FunctionDef)}
        self.assertIn("timeout",[x.arg for x in funcs["intraday_1m"].args.args])
        self.assertIsInstance(funcs["intraday_1m"].args.defaults[-1],ast.Constant)
        self.assertIsNone(funcs["intraday_1m"].args.defaults[-1].value)
        self.assertIn("timeout",[x.arg for x in funcs["_get"].args.args])
        self.assertIsNone(funcs["_get"].args.defaults[-1].value)

    def test_notifier_bounded_and_fail_open(self):
        tree=ast.parse((ROOT/"line_signal_notifier_v3.py").read_text(encoding="utf-8"))
        main=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="main")
        calls=[x for x in ast.walk(main) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=="intraday_1m"]
        self.assertEqual(len(calls),1)
        kwargs={x.arg:x.value for x in calls[0].keywords}
        self.assertEqual(kwargs["timeout"].value,2.0)
        self.assertTrue(any(isinstance(x,ast.Try) and any(isinstance(y,ast.Name) and y.id=="enrich_preview" for y in ast.walk(x)) for x in main.body))

if __name__=="__main__":
    unittest.main()
