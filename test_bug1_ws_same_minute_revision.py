# -*- coding: utf-8 -*-
"""Offline regression guard for BUG #1: same-minute WS candle revisions.

Tests the actual production_worker_v2_shared_ws.route_message() implementation.
NO network, NO LINE, NO runner, NO production state writes.
"""
import json
import queue

import production_worker_v2_shared_ws as p

DAY = "2026-09-29"
SID = "3714"
K = p.key(DAY, SID)


def msg(high=11, close=10.5, volume=100, minute="10:23:00"):
    return json.dumps({
        "data": {
            "symbol": SID,
            "date": f"{DAY}T{minute}+08:00",
            "open": 10,
            "high": high,
            "low": 9,
            "close": close,
            "volume": volume,
        }
    })


def reset():
    p._queues.clear()
    p._last_ws_minute.clear()
    p._last_ws_fingerprint.clear()
    p._last_overflow_log.clear()
    p._queues[K] = queue.Queue(maxsize=2000)
    return p._queues[K]


def consume_and_mark(q):
    row = q.get_nowait()
    p._last_ws_minute[K] = row["minute"]
    p._last_ws_fingerprint[K] = p.ws_fingerprint(row)
    return row


def main():
    # A. First version routes normally.
    q = reset()
    p.route_message(msg())
    assert q.qsize() == 1
    first = consume_and_mark(q)
    assert first["minute"] == "10:23:00"

    # B. Exact duplicate after processing is dropped.
    p.route_message(msg())
    assert q.qsize() == 0

    # C. Changed same-minute revision after processing survives.
    p.route_message(msg(high=12, close=11, volume=150))
    assert q.qsize() == 1
    rev = q.get_nowait()
    assert (rev["high"], rev["close"], rev["volume"]) == (12, 11, 150)

    # D. Pending same-minute revision coalesces to one newest row.
    q = reset()
    p.route_message(msg())
    p.route_message(msg(high=12, close=11, volume=150))
    assert q.qsize() == 1
    newest = q.get_nowait()
    assert (newest["high"], newest["close"], newest["volume"]) == (12, 11, 150)

    # E. New next minute remains normal.
    q = reset()
    p.route_message(msg())
    consume_and_mark(q)
    p.route_message(msg(high=12.5, close=12, volume=180, minute="10:24:00"))
    assert q.qsize() == 1
    nxt = q.get_nowait()
    assert nxt["minute"] == "10:24:00"

    reset()
    p._queues.clear()
    print("[PASS] first version routes")
    print("[PASS] processed exact duplicate drops")
    print("[PASS] processed changed same-minute revision survives")
    print("[PASS] pending same-minute revision coalesces")
    print("[PASS] next minute unchanged")
    print("NO NETWORK | NO LINE | NO RUNNER | NO PRODUCTION WRITE")


if __name__ == "__main__":
    main()
