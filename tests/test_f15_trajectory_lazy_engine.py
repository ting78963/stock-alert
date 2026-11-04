import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("trajectory", Path(__file__).resolve().parents[1] / "f15_trajectory_store.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TrajectoryLazyEngineTests(unittest.TestCase):
    def test_existing_records_do_not_load_engine(self):
        event = {"stock_id": "1301", "signal_class": "A", "recognition_time": "10:30"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = "2026-11-04"
            folder = root / day
            folder.mkdir()
            (folder / "1301_A_1030.json").write_text(json.dumps({
                "schema": mod.SCHEMA,
                "identity": {"date": day, "stock_id": "1301", "signal_class": "A", "recognition_time": "10:30"}
            }), encoding="utf-8")
            with patch.object(mod, "OUT", root), patch.object(mod.f15, "load_events", return_value=[event]), patch.object(mod.runpy, "run_path", side_effect=AssertionError("engine should not load")):
                result = mod.build_day(day)
            self.assertEqual(result["written"], 0)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(json.loads((folder / "manifest.json").read_text())["count"], 1)

if __name__ == "__main__":
    unittest.main()
