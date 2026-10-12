#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B historical-404 quarantine structural regression. OFFLINE, NO IMPORT, NO NETWORK."""
import ast, re, pathlib, sys
root=pathlib.Path(__file__).resolve().parent
b=(root/"production_worker_v2_shared_ws.py").read_text(encoding="utf-8")
a=(root/"fugle_a_scanner_v2_4.py").read_text(encoding="utf-8")
for name,src in [("B",b),("A",a)]:
    ast.parse(src)
    print("[PASS]",name,"syntax")
tree=ast.parse(b)
def fn(name):
    return next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
classifier=fn("_is_individual_history404")
expr=classifier.body[1].value
pattern=ast.literal_eval(expr.args[0].args[0])
cases=[
    ("Fugle HTTP 404 | daily-calendar 2323 2026-10-12",True),
    ("Fugle HTTP 404 | historical-minute 2323 2026-10-08",True),
    ("Fugle HTTP 429 | daily-calendar 2323 2026-10-12",False),
    ("Fugle HTTP 500 | daily-calendar 2323 2026-10-12",False),
    ("Fugle HTTP 404 | intraday-minute 2323 2026-10-12",False),
]
for msg,expected in cases:
    assert bool(re.search(pattern,msg)) is expected,(msg,pattern)
print("[PASS] 404 classifier: 2 positive / 3 negative")
assert 'STATE_ROOT/"b_history_404"/(day+".json")' in b
assert 'if not dry_run and _history404_has(day,sid)' in b
assert '_history404_mark(day,sid)' in b
assert '"schema":"b_history_404_v1"' in b
assert 'if obj.get("schema")!="b_history_404_v1" or obj.get("date")!=day' in b
print("[PASS] date-keyed persistent quarantine and pre-Runner skip")
assert 'if result == "history_404_skip":' in a
assert 'handoff_status="history_404_skipped"' in a
assert '"type": "b_history_404_skipped"' in a
assert 'if data.get("skipped") is True and data.get("reason") == "individual_history_404"' in a
print("[PASS] A skip separated from normal discovery")
assert 'self.mark_sent(snap_date, symbol, payload)' in a
assert 'return "history_404_skip"' in a
print("[PASS] normal A handoff path remains")
print("OFFLINE STRUCTURAL AUDIT PASS | NO RUNTIME REPLAY | NO PRODUCTION WRITE")
