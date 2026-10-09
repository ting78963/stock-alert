#!/usr/bin/env python3
"""Read-only static audit of historical 429 retry state in staged A source."""
import ast
from pathlib import Path
s=Path("/tmp/a_429_stage.py").read_text(encoding="utf-8")
t=ast.parse(s)
constants={}
for n in t.body:
    if isinstance(n,ast.Assign):
        for x in n.targets:
            if isinstance(x,ast.Name) and x.id.startswith("HISTORY_"):
                try:constants[x.id]=ast.literal_eval(n.value)
                except (ValueError,TypeError):pass
print("429_BACKOFF_SEC =",constants.get("HISTORY_429_BACKOFF_SEC"))
print("FAILURE_COOLDOWN_SEC =",constants.get("HISTORY_BACKUP_FAILURE_COOLDOWN_SEC"))
print("MAX_429_RETRIES =",constants.get("HISTORY_BACKUP_MAX_429_RETRIES"))
assert constants["HISTORY_429_BACKOFF_SEC"]==60
assert constants["HISTORY_BACKUP_FAILURE_COOLDOWN_SEC"]==15
assert constants["HISTORY_BACKUP_MAX_429_RETRIES"]==2
worker=next(x for x in t.body if isinstance(x,ast.ClassDef) and x.name=="WaitDataWorker")
run=next(x for x in worker.body if isinstance(x,ast.FunctionDef) and x.name=="_run")
finish=next(x for x in worker.body if isinstance(x,ast.FunctionDef) and x.name=="_finish")
run_text=ast.get_source_segment(s,run)
finish_text=ast.get_source_segment(s,finish)
assert 'retry budget exhausted' in run_text
assert 'fatal=True' in run_text
assert 'self.retry_after[key] = time.monotonic() + HISTORY_BACKUP_FAILURE_COOLDOWN_SEC' in finish_text
assert 'history_backoff_until = (' in run_text
print("PASS: 429 max three attempts per job; 60s wait between first retries")
print("PASS: exhausted 429 classified fatal and sent to main scanner")
print("RISK: global backoff not extended when retry budget exhausted")
print("RISK: per-symbol failure cooldown only 15s after fatal 429")
print("STATIC_AUDIT_ONLY; HTTP = NONE; PRODUCTION_WRITES = NONE")
