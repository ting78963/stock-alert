#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B previous-session daily-calendar 404 audit. Offline; no API or production writes."""
import ast
from pathlib import Path

BASE=Path(__file__).resolve().parent
SRC=BASE/"fugle_b_engine_v2_p1.py"
s=SRC.read_text(encoding="utf-8")
t=ast.parse(s)
functions={n.name:n for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
assert "fetch_prev" in functions and "fetch" in functions, "STOP: expected functions missing"
f=ast.get_source_segment(s,functions["fetch_prev"])
minute=ast.get_source_segment(s,functions["fetch"])
assert "daily-calendar" in f and '"/historical/candles/' in f, "STOP: calendar endpoint changed"
assert '"timeframe":"D"' in f, "STOP: daily timeframe changed"
assert 'if ds<date' in f, "STOP: prior-session selection changed"
assert 'pobj=fetch(key,sid,pdate)' in f, "STOP: prior minute fetch missing"
assert 'py["volume"].clip(lower=0).sum()' in f, "STOP: frozen prior volume semantics changed"
assert '"/intraday/candles/' in minute and '"/historical/candles/' in minute, "STOP: minute routing changed"
print("[PASS] B startup fetch_prev resolves prior session through daily historical candles")
print("[PASS] previous close and volume come from prior-day historical minute bars")
print("[PASS] no daily-volume substitution permitted")
print("[FINDING] A daily-calendar HTTP 404 stops B before minute-history fetch")
print("[NOT PROVEN] HTTP 404 cause: endpoint, permission, instrument coverage, or vendor response")
print("[NEXT] Compare 2323 daily candles vs known-good stock with authorized read-only API probe")
print("OFFLINE ONLY | NO NETWORK | NO PRODUCTION WRITE")
