# -*- coding: utf-8 -*-
"""Read-only 08:55 TAIEX trend adapter; no API requests, writes or LINE delivery."""
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from taiex_fugle_store_v1 import STORE, read_store
from taiex_trend_narrative_v1 import analyze_taiex
from taiex_market_history_v1 import completed_week_closes
from premarket_market_flex_v1 import build_premarket_flex

TPE=ZoneInfo("Asia/Taipei")

def load_taiex_trend(as_of=None,path=None):
    report_date=as_of or datetime.now(TPE).date()
    if isinstance(report_date,date):
        report_date=report_date.isoformat()
    report_date=str(report_date)[:10]
    target=Path(path) if path is not None else STORE
    rows=read_store(target)
    trend=analyze_taiex(rows,report_date)
    prior=[r for r in rows if r["date"]<report_date]
    trend["last_close_date"]=prior[-1]["date"] if prior else None
    trend["last_close"]=prior[-1]["close"] if prior else None
    trend["as_of"]=report_date
    trend["daily_count"]=len(prior)
    trend["completed_week_count"]=len(completed_week_closes(prior,report_date))
    trend["weekly_ma100_ready"]=trend["completed_week_count"]>=102
    return trend

def build_taiex_preview(as_of=None,path=None,indicators=None,system_status="待確認"):
    """Preview only. Never infer system health, market prices, or send LINE."""
    trend=load_taiex_trend(as_of,path)
    values=dict(indicators or {})
    if "taiex" not in values:
        target=Path(path) if path is not None else STORE
        rows=[r for r in read_store(target) if r["date"] < trend["as_of"]]
        if rows:
            current=rows[-1]
            change=None
            if len(rows)>=2:
                delta=current["close"]-rows[-2]["close"]
                change=f"{delta:+,.2f} ({delta/rows[-2]['close']:+.2%})"
            values["taiex"]={"value":f"{current['close']:,.2f}","change":change,
                             "timestamp":f"{current['date']} 收盤"}
    return build_premarket_flex(values,trend=trend,system_status=system_status)
