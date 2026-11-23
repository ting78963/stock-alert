# -*- coding: utf-8 -*-
"""08:55 market MA research snapshot; read-only, no LINE or worker integration.

Use the exact same crossover and slope functions for daily and weekly closes.
Weekly bars are grouped by ISO calendar week via existing TAIEX history code.
"""
from datetime import date
from taiex_market_history_v1 import normalize_daily, completed_week_closes
from research.strong_stock_ma_parity_v1 import ma_cross_full, ma_trend


def market_trend_snapshot(rows, as_of):
    report_date = date.fromisoformat(str(as_of)[:10])
    daily = [r for r in normalize_daily(rows) if r["date"] < report_date.isoformat()]
    weekly = completed_week_closes(daily, report_date)
    def analyze(series):
        return {
            "count": len(series),
            "ma100_ready": len(series) >= 100,
            "cross_ready": len(series) >= 101,
            "day5_history_ready": len(series) >= 105,
            "last_date": series[-1]["date"] if series else None,
            "ma": ma_trend(series, (20, 100)),
            "cross_20_100": ma_cross_full(series, 100),
        }
    return {
        "as_of": report_date.isoformat(),
        "daily": analyze(daily),
        "weekly": analyze(weekly),
    }
