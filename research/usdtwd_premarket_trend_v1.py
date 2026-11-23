# -*- coding: utf-8 -*-
"""Read-only USD/TWD MA5/20 for approved morning brief.

Uses official CBC daily closes, not a live FX quote. Never touches scanner.
"""
from datetime import date
from taiex_market_history_v1 import normalize_daily


def fx_premarket_snapshot(rows, as_of):
    day = date.fromisoformat(str(as_of)[:10]).isoformat()
    daily = [r for r in normalize_daily(rows) if r["date"] < day]
    closes = [r["close"] for r in daily]

    def ma(period, offset=0):
        end = len(closes) - offset
        if end < period:
            return None
        return sum(closes[end-period:end]) / period

    def compare(short, long):
        a, b = ma(short), ma(long)
        if a is None or b is None:
            return "insufficient"
        a0, b0 = ma(short, 1), ma(long, 1)
        if a0 is None or b0 is None:
            return "insufficient"
        if a0 < b0 and a >= b:
            return "golden_cross"
        if a0 > b0 and a <= b:
            return "death_cross"
        if a < b and a0 < b0 and b > 0 and b0 > 0:
            gap, previous = (b-a)/b*100, (b0-a0)/b0*100
            if 0 < gap <= .75 and gap < previous:
                return "prepare_golden"
        if a > b and a0 > b0 and b > 0 and b0 > 0:
            gap, previous = (a-b)/b*100, (a0-b0)/b0*100
            if 0 < gap <= .75 and gap < previous:
                return "prepare_death"
        return "above" if a > b else "below" if a < b else "equal"

    def direction(period):
        current, previous = ma(period), ma(period, 1)
        if current is None or previous is None:
            return "insufficient"
        return "rising" if current > previous else "falling" if current < previous else "flat"

    def twd_interpretation(status):
        return {
            "golden_cross": "TWD_weakening",
            "prepare_golden": "TWD_may_weaken",
            "death_cross": "TWD_strengthening",
            "prepare_death": "TWD_may_strengthen",
            "above": "TWD_weak_bias",
            "below": "TWD_strong_bias",
            "equal": "neutral",
            "insufficient": "insufficient",
        }[status]

    cross = compare(5, 20)
    return {
        "as_of": day,
        "source": "cbc_interbank_daily_close",
        "quote_kind": "official_daily_close",
        "last_close_date": daily[-1]["date"] if daily else None,
        "last_close": closes[-1] if closes else None,
        "count": len(closes),
        "ma5": ma(5),
        "ma20": ma(20),
        "ma5_direction": direction(5),
        "ma20_direction": direction(20),
        "ma5_20": cross,
        "twd_ma5_20_interpretation": twd_interpretation(cross),
        "twd_ma5_direction": {"rising":"TWD_weakening", "falling":"TWD_strengthening", "flat":"neutral", "insufficient":"insufficient"}[direction(5)],
        "twd_ma20_direction": {"rising":"TWD_weakening", "falling":"TWD_strengthening", "flat":"neutral", "insufficient":"insufficient"}[direction(20)],
    }
