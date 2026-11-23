# -*- coding: utf-8 -*-
"""Pure Python parity port of strong-stock index.html calcWatchDayMACross.

Source: ting78963/stock/index.html (calcWatchDayMACross).
Research-only: not wired into A/B/LINE or production workers.
"""
from math import isfinite


def _closes(rows):
    result = []
    for row in rows:
        try:
            value = float(row["close"])
        except (TypeError, ValueError, KeyError):
            continue
        if isfinite(value):
            result.append(value)
    return result


def daily_ma_cross(rows, long_period):
    """Return '', 'prepare', 'golden_cross', or 'golden_cross_day2'..day5."""
    if long_period not in (60, 100):
        raise ValueError("long_period must be 60 or 100")
    cl = _closes(rows)
    if len(cl) < long_period + 1:
        return ""
    def ma(end, n):
        return sum(cl[end-n:end]) / n
    n = len(cl)
    short_now, long_now = ma(n, 20), ma(n, long_period)
    short_prev, long_prev = ma(n-1, 20), ma(n-1, long_period)
    for day in range(1, 6):
        end = n - day + 1
        if end < long_period + 1:
            break
        if ma(end-1, 20) < ma(end-1, long_period) and ma(end, 20) >= ma(end, long_period):
            return "golden_cross" if day == 1 else f"golden_cross_day{day}"
    if long_now > 0 and long_prev > 0 and short_now < long_now and short_prev < long_prev:
        gap = (long_now-short_now)/long_now*100
        prev_gap = (long_prev-short_prev)/long_prev*100
        if gap > 0 and gap <= 0.75 and gap < prev_gap:
            return "prepare"
    return ""


def daily_ma_values(rows):
    cl = _closes(rows)
    return {f"ma{n}": (sum(cl[-n:])/n if len(cl) >= n else None) for n in (20, 60, 100)}
