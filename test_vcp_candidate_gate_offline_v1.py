#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evaluate the ACTUAL Scanner.scan_once candidate comprehension, offline.
No network, no production files, no runner.
"""
import ast
import inspect
import textwrap
from types import SimpleNamespace
import fugle_a_scanner_v2_4 as m

def actual_candidates(snaps, watched, sent, vol_min=4000, day="2026-10-12"):
    tree = ast.parse(textwrap.dedent(inspect.getsource(m.Scanner.scan_once)))
    assignments = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "candidates" for t in n.targets)]
    assert len(assignments) == 1 and isinstance(assignments[0].value, ast.ListComp)
    expr = ast.Expression(body=assignments[0].value)
    ast.fix_missing_locations(expr)
    class FakeScanner:
        selector = SimpleNamespace(basic_code_ok=m.StrongSelector.basic_code_ok)
        state = {"vcp_near_watch": {day: watched}}
        def already_sent(self, d, symbol):
            return (d, symbol) in sent
    return eval(compile(expr, "<actual scan_once candidates>", "eval"),
                {"self": FakeScanner(), "snaps": snaps, "snap_date": day, "vol_min": vol_min})

def snap(symbol, volume, change):
    return {"stock_id": symbol, "total_volume": volume, "change_rate": change}

def main():
    d = "2026-10-12"
    snaps = [snap("3714", 800, -0.5), snap("2457", 1000, -1.0),
             snap("4906", 800, 0.1), snap("1711", 799, 3.0),
             snap("0050", 10000, 2.0), snap("8105", 2000, 2.0)]
    got = actual_candidates(snaps, {"3714": {"armed_at": "09:20"}},
                            {(d, "8105")})
    ids = [x["stock_id"] for x in got]
    assert ids == ["3714", "2457", "4906"], ids
    print("[PASS] armed VCP still scanned during negative change")
    print("[PASS] unarmed negative stock is now eligible for VCP; positive 800 stock allowed")
    print("[PASS] 799 lots blocked; ETF blocked; successful shared handoff deduped")
    got2 = actual_candidates([snap("3714", 1800, -4.0)],
                             {"3714": {"pending_breakout": {"confirmed_at": "09:35"}}}, set())
    assert [x["stock_id"] for x in got2] == ["3714"]
    print("[PASS] pending breakout retry remains candidate after price pullback")
    print("OFFLINE ONLY | ACTUAL CANDIDATE EXPRESSION | NO NETWORK | NO PRODUCTION WRITE")

if __name__ == "__main__":
    main()
