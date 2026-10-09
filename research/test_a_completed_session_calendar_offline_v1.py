#!/usr/bin/env python3
"""Offline deterministic TWSE completed-session resolver audit. No HTTP or writes."""
import importlib.util, sys
from datetime import date, timedelta
from pathlib import Path
path=Path("twse_session_gate_v1.py")
if not path.is_file(): raise SystemExit("STOP: twse_session_gate_v1.py missing in working directory")
spec=importlib.util.spec_from_file_location("twse_session_gate_offline",path)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
# Explicit fixture, NOT an assertion that live TWSE data was fetched.
rows=[
    {"Date":"1151009","Name":"國慶日補假，停止交易"},
    {"Date":"1151010","Name":"國慶日，停止交易"},
]
def previous_completed(today,rows):
    d=today-timedelta(days=1)
    for _ in range(15):
        if m.is_scheduled_open(d,rows=rows):
            return d
        d-=timedelta(days=1)
    raise AssertionError("STOP: no prior session in 15 days")
tests=[
    (date(2026,10,8),date(2026,10,7)),
    (date(2026,10,9),date(2026,10,8)),
    (date(2026,10,10),date(2026,10,8)),
    (date(2026,10,11),date(2026,10,8)),
    (date(2026,10,12),date(2026,10,8)),
    (date(2026,10,13),date(2026,10,12)),
]
for today,expected in tests:
    got=previous_completed(today,rows)
    assert got==expected,(today,got,expected)
    print(f"PASS: snapshot={today} required_completed={got}")
try:
    previous_completed(date(2027,1,4),rows)
except m.SessionGateError:
    print("PASS: calendar missing year fails closed")
else:
    raise AssertionError("STOP: calendar year coverage not enforced")
print("OFFLINE_ONLY = YES")
print("NEXT = verify real official calendar once, persist vetted session watermark, compare DB coverage")
