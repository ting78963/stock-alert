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

    def test_market_worker_is_standalone(self):
        production=ast.parse((ROOT/"production_worker_v1.py").read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(node,ast.ImportFrom) and node.module=="market_data_maintenance_v1" for node in ast.walk(production)))
        market_worker=ast.parse((ROOT/"market_data_worker_v1.py").read_text(encoding="utf-8"))
        modules={node.module for node in ast.walk(market_worker) if isinstance(node,ast.ImportFrom)}
        self.assertIn("market_data_maintenance_v1",modules)
        self.assertIn("usdtwd_cbc_maintenance_v1",modules)
        self.assertFalse(any(m and m.startswith("f15_") for m in modules))

    def test_before_1430_does_not_fetch(self):
        now=datetime(2026,11,23,14,29,tzinfo=ZoneInfo("Asia/Taipei"))
        with patch("taiex_fugle_store_v1.update") as update:
            self.assertEqual(market.maintain_taiex_once(now),"not_due")
            update.assert_not_called()

    def test_1430_does_not_wait_for_f15(self):
        now=datetime(2026,11,23,14,30,tzinfo=ZoneInfo("Asia/Taipei"))
        from types import ModuleType
        gate=ModuleType("twse_session_gate_v1")
        gate.is_scheduled_open=lambda day: True
        with patch.dict("sys.modules",{"twse_session_gate_v1":gate}), patch("taiex_fugle_store_v1.read_store",return_value=[]), patch("taiex_fugle_store_v1.update",return_value={"latest":"2026-11-23","stored":500,"snapshot":{"daily_ma100":1,"weekly_ma100":1}}) as update:
            self.assertEqual(market.maintain_taiex_once(now),"updated")
            update.assert_called_once()

    def test_1505_preserves_buffer_before_stock_maintenance(self):
        now=datetime(2026,11,23,15,5,tzinfo=ZoneInfo("Asia/Taipei"))
        with patch("taiex_fugle_store_v1.update") as update:
            self.assertEqual(market.maintain_taiex_once(now),"not_due")
            update.assert_not_called()

    def test_1530_is_reserved_for_existing_stock_maintenance(self):
        now=datetime(2026,11,23,15,30,tzinfo=ZoneInfo("Asia/Taipei"))
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
