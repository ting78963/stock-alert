# -*- coding: utf-8 -*-
"""Regression guard: market-data maintenance is independent of F15 delivery."""
import ast
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
import market_data_maintenance_v1 as market

ROOT=Path(__file__).resolve().parents[1]

class MarketMaintenanceIsolationTests(unittest.TestCase):
    def test_f15_report_has_no_market_data_maintenance(self):
        tree=ast.parse((ROOT/"f15_eod_signal_report.py").read_text(encoding="utf-8"))
        names={node.name for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
        self.assertNotIn("maintain_taiex_once",names)
        self.assertFalse(any(isinstance(node,ast.ImportFrom) and node.module=="market_data_maintenance_v1" for node in ast.walk(tree)))

    def test_worker_starts_separate_market_thread(self):
        tree=ast.parse((ROOT/"production_worker_v1.py").read_text(encoding="utf-8"))
        imports=[node for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module=="market_data_maintenance_v1"]
        self.assertEqual(len(imports),1)
        self.assertTrue(any(alias.name=="loop" and alias.asname=="market_data_loop" for alias in imports[0].names))
        self.assertIn("market-data-maintenance",(ROOT/"production_worker_v1.py").read_text(encoding="utf-8"))

    def test_before_1530_does_not_fetch(self):
        now=datetime(2026,11,23,15,29,tzinfo=ZoneInfo("Asia/Taipei"))
        with patch("taiex_fugle_store_v1.update") as update:
            self.assertEqual(market.maintain_taiex_once(now),"not_due")
            update.assert_not_called()

    def test_weekend_does_not_fetch(self):
        now=datetime(2026,11,22,16,0,tzinfo=ZoneInfo("Asia/Taipei"))
        with patch("taiex_fugle_store_v1.update") as update:
            self.assertEqual(market.maintain_taiex_once(now),"not_due")
            update.assert_not_called()

if __name__=="__main__":
    unittest.main()
