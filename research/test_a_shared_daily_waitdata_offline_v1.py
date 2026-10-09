#!/usr/bin/env python3
"""Offline WAIT_DATA behavior tests; no Fugle requests, no production writes."""
import importlib.util
import os
import sys
import time
from pathlib import Path

path = os.environ.get("A_TEST_MODULE", "/tmp/fugle_a_scanner_db_test.py")
spec = importlib.util.spec_from_file_location("a_wait_data_under_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

# Build worker without starting a thread or touching any production state.
worker = object.__new__(mod.WaitDataWorker)
worker.jobs = mod.queue.Queue(maxsize=2)
worker.results = mod.queue.Queue()
worker.pending = set()
worker.retry_after = {}
worker.pending_lock = mod.threading.Lock()
symbol, day = "1101", "2026-10-12"
key = (symbol, day)
assert worker.submit(symbol, day) is True
assert worker.submit(symbol, day) is False
assert worker.jobs.qsize() == 1
print("PASS: duplicate pending jobs suppressed")

worker._finish(mod.WaitDataResult(symbol=symbol, snapshot_date=day, ok=False, error="offline test", fatal=False))
assert worker.submit(symbol, day) is False
assert worker.retry_after[key] > time.monotonic()
print("PASS: failure triggers cooldown")

worker.retry_after[key] = time.monotonic() - 1
assert worker.submit(symbol, day) is True
print("PASS: retry allowed after cooldown")

worker._finish(mod.WaitDataResult(symbol=symbol, snapshot_date=day, ok=True, rows=[], covered_through="2026-10-11"))
assert key not in worker.retry_after
print("PASS: successful result clears cooldown")

# DB-first direct read, with HTTP path forcibly forbidden.
mod.http_json = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("UNEXPECTED FUGLE HTTP"))
os.environ["A_LAST_COMPLETED_SESSION"] = "2026-10-08"
os.environ.pop("A_SHARED_DAILY_DB", None)
adapter = mod.FugleAdapter("OFFLINE_TEST")
adapter.history_cache = {}
adapter.daily_cache = {}
bars = adapter.daily_history_local_ready(symbol, day)
assert bars is not None and len(bars) > 0
print(f"PASS: A DB-first local daily rows={len(bars)}, HTTP forbidden")
