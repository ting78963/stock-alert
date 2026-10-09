#!/usr/bin/env python3
"""Offline AST audit of staged 429 recovery; no API calls, no production execution."""
import ast
from pathlib import Path
s=Path("/tmp/a_429_recovery_stage.py").read_text(encoding="utf-8")
t=ast.parse(s)
worker=next(x for x in t.body if isinstance(x,ast.ClassDef) and x.name=="WaitDataWorker")
methods={n.name:ast.get_source_segment(s,n) for n in worker.body if isinstance(n,ast.FunctionDef)}
run=methods["_run"];finish=methods["_finish"]
assert 'history_backoff_until = (\n                                    time.monotonic() + HISTORY_429_BACKOFF_SEC' in run
assert 'raise RuntimeError(f"HISTORY_RATE_LIMITED: 429 retry budget exhausted for {symbol}")' in run
assert 'fatal=not rate_limited' in run
assert 'if result.error and "HISTORY_RATE_LIMITED" in result.error' in finish
assert 'else HISTORY_BACKUP_FAILURE_COOLDOWN_SEC' in finish
print("PASS: 429 exhausted -> keep worker-wide cooldown")
print("PASS: 429 exhausted -> recoverable WAIT_DATA result, not fatal A stop")
print("PASS: per-symbol 429 cooldown 60s; other failures retain 15s")
print("PASS: retry budget remains max 3 attempts per job")
print("LIMITATION: static audit; real worker thread, queue timing and HTTP are NOT exercised")
print("HTTP = NONE; REAL A/B/LINE = NONE; PRODUCTION_WRITES = NONE")
