#!/usr/bin/env python3
"""Offline scan_once integration smoke test. No network, production writes, or LINE."""
import importlib.util
import os
import sys
import unittest.mock as mock
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ["A_F11_OFFLINE_STAGING"] = "1"
spec = importlib.util.spec_from_file_location("a_f11_under_test", "/tmp/a_f11_offline_staging_test.py")
a = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = a
spec.loader.exec_module(a)
adapter = a.FugleAdapter("OFFLINE_TEST")
good = next(s for s, v in adapter.f11_metadata_cache.items()
            if v.get("market") == "TSE" and v.get("securityType") == "01"
            and str(v.get("industry")) not in a.EXCLUDED_INDUSTRY_CODES
            and a.StrongSelector.basic_code_ok(s))
missing = "9999"  # Valid four-digit code, absent from offline F11 staging cache
assert a.StrongSelector.basic_code_ok(missing)
assert missing not in adapter.f11_metadata_cache
today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
snaps = [{"stock_id": sym, "date": today, "change_rate": 3.0,
          "total_volume": 10000.0, "total_amount": 100000000.0,
          "close": 100.0, "market": "TSE", "name": sym}
         for sym in (missing, good)]
adapter.snapshot = mock.Mock(return_value=snaps)
adapter.daily_history_local_ready = mock.Mock(return_value=None)
a.http_json = mock.Mock(side_effect=AssertionError("HTTP_FORBIDDEN"))
a.save_json_atomic = mock.Mock(side_effect=AssertionError("FILE_WRITE_FORBIDDEN"))
a.append_event = mock.Mock(side_effect=AssertionError("EVENT_WRITE_FORBIDDEN"))
a.append_queue_shadow = mock.Mock(side_effect=AssertionError("SHADOW_WRITE_FORBIDDEN"))
a.record_a_scan_mother_identity = mock.Mock()
scanner = object.__new__(a.Scanner)
scanner.adapter = adapter
scanner.selector = a.StrongSelector()
scanner.state = {"discovered": {}, "queue_waiting": {}, "volume_armed": {}}
scanner.already_sent = mock.Mock(return_value=False)
scanner.liquidity_minimum = mock.Mock(return_value=2000)
scanner.apply_wait_data_results = mock.Mock(return_value=0)
scanner.queue_entered_at = mock.Mock(return_value="2026-10-09T09:01:00+08:00")
scanner.wait_data_worker = mock.Mock()
scanner.wait_data_worker.submit.return_value = True
result = scanner.scan_once()
assert scanner.liquidity_minimum.call_count == 1
assert adapter.daily_history_local_ready.call_count == 1, "valid stock not processed"
assert adapter.daily_history_local_ready.call_args.args[0] == good
scanner.wait_data_worker.submit.assert_called_once_with(good, today)
assert a.http_json.call_count == 0
assert a.save_json_atomic.call_count == 0
assert a.append_event.call_count == 0
assert a.append_queue_shadow.call_count == 0
assert not a.record_a_scan_mother_identity.call_args_list or all(
    c.args[1] == good for c in a.record_a_scan_mother_identity.call_args_list)
print("FIRST_GATE_CANDIDATES = 2 (see scanner diagnostic above)")
print("SCAN_ONCE_F11_MISS_CONTINUES = PASS")
print("VALID_STOCK_HISTORY_QUEUED =", good)
print("HTTP_CALLS = 0; PRODUCTION_WRITES = 0")
print("RESULT = PASS")
