# -*- coding: utf-8 -*-
"""TAIEX closing-price history and moving averages. Pure calculations; no A/B/F15 signal changes."""
from __future__ import annotations
from datetime import date, timedelta
from math import isfinite


def normalize_daily(rows):
    """Accept date/close records, sort ascending, reject conflicting duplicate dates."""
    by_day = {}
    for row in rows:
        day = date.fromisoformat(str(row["date"])[:10])
        close = float(row["close"])
        if not isfinite(close) or close <= 0:
            raise ValueError(f"Invalid TAIEX close: {day}")
        key = day.isoformat()
        if key in by_day and by_day[key] != close:
            raise ValueError(f"Conflicting TAIEX close: {key}")
        by_day[key] = close
    return [{"date": d, "close": by_day[d]} for d in sorted(by_day)]


def completed_week_closes(daily, as_of):
    """Only fully ended ISO calendar weeks. A holiday-shortened week is complete after Friday."""
    day = date.fromisoformat(str(as_of)[:10])
    cutoff = day - timedelta(days=day.weekday())  # Monday of current week
    weeks = {}
    for row in normalize_daily(daily):
        d = date.fromisoformat(row["date"])
        if d >= cutoff:
            continue
        iso = d.isocalendar()
        weeks[(iso.year, iso.week)] = row
    return list(weeks.values())


def _ma(values, n):
    return round(sum(values[-n:]) / n, 4) if len(values) >= n else None


def snapshot(rows, as_of):
    """As-of is the report date. Never use today's incomplete trading session."""
    report_day = date.fromisoformat(str(as_of)[:10])
    daily = [r for r in normalize_daily(rows) if r["date"] < report_day.isoformat()]
    weekly = completed_week_closes(daily, report_day)
    dc = [r["close"] for r in daily]
    wc = [r["close"] for r in weekly]
    return {
        "schema": "taiex_ma_v1",
        "as_of": report_day.isoformat(),
        "last_close_date": daily[-1]["date"] if daily else None,
        "last_close": dc[-1] if dc else None,
        "daily_count": len(dc),
        "completed_week_count": len(wc),
        "daily_ma20": _ma(dc, 20),
        "daily_ma100": _ma(dc, 100),
        "weekly_ma20": _ma(wc, 20),
        "weekly_ma100": _ma(wc, 100),
    }
