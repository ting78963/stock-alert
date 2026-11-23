# -*- coding: utf-8 -*-
"""Offline, read-only TAIEX cache audit for premarket readiness.

Usage: python taiex_cache_audit_v1.py [YYYY-MM-DD] [cache-path]
No API requests, writes, or LINE sends.
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from premarket_taiex_adapter_v1 import load_taiex_trend
from taiex_fugle_store_v1 import STORE

def audit(as_of=None, path=None):
    report_date = as_of or datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    target = Path(path) if path is not None else STORE
    trend = load_taiex_trend(report_date, target)
    latest = trend["last_close_date"]
    age_days = (date.fromisoformat(str(report_date)[:10]) - date.fromisoformat(latest)).days if latest else None
    return {
        "schema": "taiex_cache_audit_v1",
        "as_of": str(report_date)[:10],
        "cache_exists": target.is_file(),
        "last_close_date": latest,
        "last_close": trend["last_close"],
        "last_close_age_calendar_days": age_days,
        "daily_count": trend["daily_count"],
        "completed_week_count": trend["completed_week_count"],
        "daily_ma100_ready": trend["daily_count"] >= 102,
        "weekly_ma100_ready": trend["weekly_ma100_ready"],
        "headline": trend["headline"],
        "warning": ("歷史資料不足" if trend["headline"] == "資料不足"
                    else "最新收盤日距報告日超過14天，請確認是否停更" if age_days is not None and age_days > 14
                    else None),
    }

if __name__ == "__main__":
    print(json.dumps(audit(*(sys.argv[1:3])), ensure_ascii=False, indent=2))
