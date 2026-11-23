# -*- coding: utf-8 -*-
"""Read-only 08:55 TAIEX trend adapter; no API requests, writes or LINE delivery."""
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from taiex_fugle_store_v1 import STORE, read_store
from taiex_trend_narrative_v1 import analyze_taiex
from taiex_market_history_v1 import completed_week_closes
from premarket_market_flex_v1 import build_premarket_flex
from premarket_quote_policy_v1 import validate_quote
from usdtwd_premarket_compare_v1 import compare_live_to_cbc_close
from usdtwd_cbc_daily_v1 import trend_snapshot as fx_trend_snapshot

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

def build_taiex_preview(as_of=None,path=None,indicators=None,system_status="待確認",report_at=None,cbc_fx_rows=None):
    """Preview only. Never infer system health, market prices, or send LINE."""
    trend=load_taiex_trend(as_of,path)
    values=dict(indicators or {})
    raw_fx=values.get("usdtwd")
    if any(k in values for k in ("tx","usdtwd","sox")):
        if report_at is None:
            raise ValueError("report_at required for externally sourced market quotes")
        for key in ("tx","usdtwd","sox"):
            if key in values:
                values[key]=validate_quote(key,values[key],report_at)
    if raw_fx is not None and cbc_fx_rows is not None:
        comparison=compare_live_to_cbc_close(raw_fx,cbc_fx_rows,report_at)
        fx=values.get("usdtwd") or {}
        if comparison["status"]=="ok" and fx.get("status")=="live":
            fx["change"]=f"{comparison['usd_twd_change']:+.4f} ({comparison['usd_twd_change_percent']:+.2f}%) · "+("臺幣貶值" if comparison["direction"]=="TWD_depreciation" else "臺幣升值" if comparison["direction"]=="TWD_appreciation" else "持平")
            fx["timestamp"]+=f"｜對照央行 {comparison['previous_close_date']} 收盤（不同來源）"
        elif fx.get("status")=="live":
            fx["timestamp"]+="｜央行前收比較資料不足"
        fx_trend=fx_trend_snapshot(cbc_fx_rows,report_at.astimezone(TPE).date())
        ma5,ma20=fx_trend["daily_ma5"],fx_trend["daily_ma20"]
        if ma5 is not None and ma20 is not None:
            fx["timestamp"]+=f"｜央行日 MA5 {ma5:.3f} / MA20 {ma20:.3f}"
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
