#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline VCP / old A shared-handoff regression. No network or production writes."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import fugle_a_scanner_v2_4 as m

def run():
    # VCP watch and breakout are independent from the common handoff dedupe.
    fresh = {"isNew": True, "dayCount": 1, "broken": False}
    assert m.vcp_handoff_decision(799, "final_contraction", False, {}, False, False) == (False, False)
    assert m.vcp_handoff_decision(800, "final_contraction", False, {}, False, False) == (True, False)
    assert m.vcp_handoff_decision(1100, "final_contraction", False, {}, True, False) == (False, False)
    assert m.vcp_handoff_decision(1500, "just_broke", True, fresh, True, False) == (False, True)
    assert m.vcp_handoff_decision(1800, "contracting", False, {}, True, True) == (False, True)
    assert m.vcp_handoff_decision(1800, "tracking", False, {}, True, False) == (False, False)
    with tempfile.TemporaryDirectory(prefix="vcp_dedupe_") as d:
        scanner = object.__new__(m.Scanner)
        scanner.state = {"discovered": {}, "volume_armed": {}, "queue_waiting": {}, "vcp_near_watch": {}}
        attempts = []
        fail_once = [True]
        def bridge(payload):
            attempts.append((payload["stock_id"], payload["source"]))
            if fail_once[0]:
                fail_once[0] = False
                raise ConnectionError("injected bridge failure")
        scanner.bridge_send = bridge
        hit_vcp = {"code": "3714", "name": "TEST", "source": "VCP", "volRatio": 2.0, "chgPct": 3.0}
        hit_a = dict(hit_vcp, source="NO_VCP")
        with patch.object(m, "STATE_FILE", Path(d) / "state.json"), patch.object(m, "append_event", lambda event: None):
            try:
                scanner.handoff_hit(hit_vcp, "2026-10-12")
                raise AssertionError("failure must propagate")
            except ConnectionError:
                pass
            assert not scanner.already_sent("2026-10-12", "3714"), "failed bridge cannot dedupe"
            assert scanner.handoff_hit(hit_vcp, "2026-10-12") is True
            assert scanner.already_sent("2026-10-12", "3714")
            assert scanner.handoff_hit(hit_a, "2026-10-12") is False, "old A must not duplicate VCP"
            assert len(attempts) == 2
            assert scanner.handoff_hit(hit_a, "2026-10-13") is True, "dedupe must be per day"
    print("[PASS] VCP 799/800/watch/breakout/pending")
    print("[PASS] bridge fail -> retry -> VCP handoff -> old A blocked same day")
    print("[PASS] next trading date may handoff")
    print("OFFLINE ONLY | NO NETWORK | NO PRODUCTION WRITE")

if __name__ == "__main__":
    run()
