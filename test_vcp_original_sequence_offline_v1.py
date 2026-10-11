#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only deterministic state-transition audit of ORIGINAL VCP formula.
No network, no production files, no changes to scanner logic.
"""
from datetime import date, timedelta
import fugle_a_scanner_v2_4 as m

def main():
    # Three increasingly narrow 20-day close ranges; 60 historical days.
    closes = (
        [100 + (i % 2) * 12 for i in range(20)] +
        [103 + (i % 2) * 5 for i in range(20)] +
        [104 + (i % 2) * 1 for i in range(20)]
    )
    volumes = [1000.0] * 60
    dates = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(60)]
    day = "2026-03-02"
    s = m.StrongSelector(track_path=None)
    watch = False
    pending = False
    observations = []
    # Each tuple is one successive snapshot of the same trading day.
    for label, price, vol in [
        ("below_800", 104.0, 799.0),
        ("first_eligible", 104.0, 800.0),
        ("still_near", 104.0, 1100.0),
        ("price_and_volume_break", 120.0, 1500.0),
        ("repeat_same_day", 120.5, 1700.0),
        ("pullback", 103.0, 1800.0),
    ]:
        if vol < 800:
            observations.append((label, "NOT_SCANNED", False, False, False, None))
            continue
        v = s.analyze_vcp(closes + [price], volumes + [vol], "3714", dates + [day])
        track = v.get("breakoutTrack") or {}
        arm, ready = m.vcp_handoff_decision(vol, v["status"], bool(v["justBroke"]), track, watch, pending)
        if arm:
            watch = True
        if ready:
            pending = True
        observations.append((label, v["status"], bool(v["justBroke"]), arm, ready, track))
    print("ORIGINAL VCP | DETERMINISTIC SAME-DAY SEQUENCE | NO NETWORK")
    for label, status, just, arm, ready, track in observations:
        print(f"{label:24s} status={status:20s} justBroke={just} arm={arm} handoff_ready={ready} track={track}")
    assert observations[0][1] == "NOT_SCANNED"
    assert observations[1][3] is True, "800 lots should arm when original VCP is final_contraction"
    assert observations[3][4] is True, "first real breakout should handoff"
    assert observations[4][4] is True, "pending handoff must survive repeated same-day analysis"
    assert observations[5][4] is True, "pending handoff must survive price pullback"
    print("[PASS] original VCP continuous-state replay: near -> first breakout -> pending retry")
    print("OFFLINE ONLY | NO NETWORK | NO PRODUCTION WRITE")

if __name__ == "__main__":
    main()
