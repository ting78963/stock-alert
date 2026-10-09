#!/usr/bin/env python3
"""429 behavior test: fake Fugle, zero network, no production writes."""
import importlib.util
import os
import sys
import time

p = os.environ.get("A_TEST_MODULE", "/tmp/fugle_a_scanner_db_test.py")
spec = importlib.util.spec_from_file_location("a_429_offline", p)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

m.HISTORY_429_BACKOFF_SEC = 0.01
calls = []
def fake_http(url, api_key):
    calls.append(url)
    raise m.AuditStop("Fugle HTTP 429 (offline injected)")
m.http_json = fake_http

w = m.WaitDataWorker("OFFLINE_TEST", max_pending=2)
key = ("1101", "2026-10-12")
assert w.submit(*key) is True
assert w.submit(*key) is False
deadline = time.monotonic() + 3
results = []
while time.monotonic() < deadline and not results:
    results = w.drain_results()
    if not results:
        time.sleep(0.01)
assert len(results) == 1, f"missing result: {results}"
assert not results[0].ok, results[0]
assert len(calls) == 3, f"expected 3 API attempts, got {len(calls)}"
assert "retry budget exhausted" in (results[0].error or ""), results[0]
print("PASS: 429 gives 3 attempts total, then stops")
assert w.submit(*key) is False
print("PASS: cooldown prevents immediate requeue")
assert len(calls) == 3
print("PASS: all requests mocked; zero real HTTP")
