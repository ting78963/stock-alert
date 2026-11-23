# -*- coding: utf-8 -*-
"""Read-only adapter for existing ting78963/stock Yahoo ^SOX quote fields.

No network calls, scheduling, or scanner changes. Require a dated US market close;
never label an undated quote as the latest completed session.
"""
from datetime import date
from math import isfinite


def sox_close_snapshot(quote, close_date, report_date):
    if not isinstance(quote, dict) or not close_date:
        return {"available": False, "reason": "missing_quote_or_date"}
    try:
        close_day = date.fromisoformat(str(close_date)[:10])
        report_day = date.fromisoformat(str(report_date)[:10])
        if close_day > report_day:
            return {"available": False, "reason": "future_close_date"}
        price = float(quote.get("close"))
        previous = float(quote.get("prev"))
        if not all(isfinite(v) and v > 0 for v in (price, previous)):
            raise ValueError("invalid price")
        change_pct = (price / previous - 1) * 100
    except (TypeError, ValueError, OverflowError):
        return {"available": False, "reason": "invalid_quote"}
    return {"available": True, "source": "yahoo_finance_sox",
            "quote_kind": "completed_session_close",
            "close_date": close_day.isoformat(),
            "close": price, "previous_close": previous,
            "change_pct": round(change_pct, 2)}
