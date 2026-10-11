#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only structural audit of actual A scanner scan_once; no API/runner/writes."""
import ast
import inspect
import textwrap
import fugle_a_scanner_v2_4 as m

def main():
    src = textwrap.dedent(inspect.getsource(m.Scanner.scan_once))
    tree = ast.parse(src)
    fn = tree.body[0]
    def line(fragment):
        matches = [i + 1 for i, s in enumerate(src.splitlines()) if fragment in s]
        assert matches, f"source fragment absent: {fragment}"
        return matches[0]
    positions = {
        "snapshot": line("self.adapter.snapshot()"),
        "candidate_gate": line("candidates = ["),
        "metadata": line("self.adapter.ticker(symbol)"),
        "history": line("self.adapter.daily_history_local_ready(symbol, snap_date)"),
        "wait_data": line("self.wait_data_worker.submit(symbol, snap_date)"),
        "queue_sort": line("prepared.sort(key=lambda x: (x[0], x[1]))"),
        "vcp_analyze": line("self.selector.analyze_vcp(vcp_closes, vcp_vols, symbol, vcp_dates)"),
        "vcp_handoff": line("handed = self.handoff_hit(vcp_hit, snap_date)"),
        "old_a_anomaly": line("self.adapter.estimated_vr5_parts("),
    }
    assert positions["snapshot"] < positions["candidate_gate"] < positions["metadata"]
    assert positions["metadata"] < positions["history"] < positions["queue_sort"] < positions["vcp_analyze"]
    assert positions["history"] < positions["wait_data"] < positions["queue_sort"]
    assert positions["vcp_analyze"] < positions["vcp_handoff"] < positions["old_a_anomaly"]
    print("ACTUAL SCAN_ONCE STRUCTURAL ORDER (function-relative lines)")
    for name, n in positions.items():
        print(f"{name:20s} line={n}")
    print("[PASS] VCP uses same prepared queue and waits for metadata + daily history")
    print("[PASS] VCP evaluates before old A anomaly inside its own queued turn")
    comps = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "candidates" for t in n.targets)]
    assert len(comps) == 1 and isinstance(comps[0].value, ast.ListComp)
    expr = ast.unparse(comps[0].value)
    print("CANDIDATE EXPRESSION:", expr[:550])
    assert 'change_rate' in expr and 'vcp_near_watch' in expr
    print("[RISK] First-time VCP observation still requires positive change rate")
    print("[RISK] VCP processing shares old A FIFO; no measured latency from static audit")
    print("OFFLINE ONLY | NO NETWORK | NO PRODUCTION WRITE")

if __name__ == "__main__":
    main()
