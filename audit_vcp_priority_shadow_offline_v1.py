#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only structural and deterministic VCP priority shadow audit."""
import ast
import inspect
import textwrap
import fugle_a_scanner_v2_4 as m

def main():
    src = textwrap.dedent(inspect.getsource(m.Scanner.scan_once))
    tree = ast.parse(src)
    assert "prepared.sort(key=lambda x: (x[0], x[1]))" in src, "STOP: old A FIFO baseline changed"
    assert "self.adapter.daily_history_local_ready(symbol, snap_date)" in src, "STOP: shared cache missing"
    assert "self.selector.analyze_vcp(vcp_closes, vcp_vols, symbol, vcp_dates)" in src
    assert "self.handoff_hit(vcp_hit, snap_date)" in src
    assert "self.handoff_hit(hit, snap_date)" in src
    assert "pending_breakout" in src
    assert "float(s.get(\"change_rate\") or 0) > 0" in src
    assert "float(s.get(\"total_volume\") or 0) >= min(vol_min, 800)" in src
    # Model a shadow ordering only; do not execute Scanner or alter queue.
    rows = [
        (1, "09:01:00", "OLD_A_1", False, False),
        (2, "09:02:00", "OLD_A_2", False, False),
        (4, "09:03:00", "VCP_WATCH", True, False),
        (4, "09:04:00", "VCP_PENDING", True, True),
    ]
    old_a = sorted(rows, key=lambda x: (x[0], x[1]))
    vcp_shadow = sorted(rows, key=lambda x: (0 if x[4] else 1 if x[3] else 2, x[0], x[1]))
    assert [x[2] for x in old_a] == ["OLD_A_1", "OLD_A_2", "VCP_WATCH", "VCP_PENDING"]
    assert [x[2] for x in vcp_shadow][:2] == ["VCP_PENDING", "VCP_WATCH"]
    print("[PASS] production baseline still old A priority + FIFO")
    print("[PASS] same cached daily-history path is used")
    print("[PASS] both routes share handoff_hit")
    print("[PASS] positive change and 800-lot first-entry constraints present")
    print("CONTROL:", " -> ".join(x[2] for x in old_a))
    print("VCP SHADOW:", " -> ".join(x[2] for x in vcp_shadow))
    print("[LIMIT] Priority improvement is hypothetical, not measured live latency")
    print("[LIMIT] No runtime queue modification; no API requests")
    print("OFFLINE ONLY | NO NETWORK | NO PRODUCTION WRITE")

if __name__ == "__main__":
    main()
