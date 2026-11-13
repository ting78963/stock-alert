"""Isolated checks for A -> B -> LINE recognition source display (no LINE send)."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class RecognitionSourceTest(unittest.TestCase):
    def test_source_carried_from_a_to_b_to_event(self):
        a = (ROOT / "fugle_a_scanner_v2_4.py").read_text(encoding="utf-8")
        worker = (ROOT / "production_worker_v2_shared_ws.py").read_text(encoding="utf-8")
        runner = (ROOT / "fugle_b_live_runner_v2_p1_final.py").read_text(encoding="utf-8")
        self.assertIn('"source": hit["source"]', a)
        self.assertIn('recognition_source=str(payload.get("source") or "").strip()', worker)
        self.assertIn('self.recognition_source=str(recognition_source or "").strip()', runner)
        self.assertEqual(runner.count('"recognition_source":self.recognition_source'), 2)

    def test_layered_flow_source_is_not_legacy_no_vcp(self):
        a = (ROOT / "fugle_a_scanner_v2_4.py").read_text(encoding="utf-8")
        self.assertIn('"source": "FLOW" if self.layered_a_enabled else "NO_VCP"', a)
        self.assertIn('if chosen and self.layered_a_enabled and chosen.get("source") == "NO_VCP":', a)
        self.assertIn('chosen["source"] = "FLOW"', a)
        self.assertIn('"source": "SURGE"', a)
        self.assertIn('result["source"] = "VCP"', a)

    def test_flex_displays_source_without_changing_retry_key(self):
        src = (ROOT / "line_signal_notifier_v3.py").read_text(encoding="utf-8")
        self.assertIn('f"辨識來源：{source}"', src)
        tree = ast.parse(src)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "retry_key")
        self.assertNotIn("recognition_source", ast.unparse(fn))

if __name__ == "__main__":
    unittest.main()
