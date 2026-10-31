"""Indicator source contract: no extra Fugle request during LINE delivery."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).parent

class IndicatorSourceTests(unittest.TestCase):
    def test_notifier_reads_local_canonical_minutes(self):
        tree=ast.parse((ROOT/"line_signal_notifier_v3.py").read_text(encoding="utf-8"))
        main=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="main")
        names={x.id for x in ast.walk(main) if isinstance(x,ast.Name)}
        self.assertNotIn("intraday_1m",names)
        self.assertIn("compute_indicators",names)
        self.assertIn("enrich_preview",names)
        self.assertIn("minute_file",names)
        self.assertIn("minutes",names)
        self.assertTrue(any(isinstance(x,ast.Try) and "enrich_preview" in
            {y.id for y in ast.walk(x) if isinstance(y,ast.Name)} for x in main.body))

    def test_original_fugle_adapter_signature_preserved(self):
        tree=ast.parse((ROOT/"fugle_adapter.py").read_text(encoding="utf-8"))
        funcs={x.name:x for x in tree.body if isinstance(x,ast.FunctionDef)}
        args=[x.arg for x in funcs["intraday_1m"].args.args]
        self.assertEqual(args,["symbol","date","key"])

if __name__=="__main__":
    unittest.main()
