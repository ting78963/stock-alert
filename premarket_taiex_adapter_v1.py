# -*- coding: utf-8 -*-
"""Read-only 08:55 TAIEX trend adapter; no API requests, writes or LINE delivery."""
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from taiex_fugle_store_v1 import STORE, read_store
from taiex_trend_narrative_v1 import analyze_taiex
from research.premarket_risk_waterline_v1 import analyze_history
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
    trend["waterline"]=analyze_history(rows,report_date)
    above=trend["waterline"].get("above",{})
    if above:
        regime="偏多" if above[20] and above[100] else "偏空" if not above[20] and not above[100] else "整理"
        trend["price_regime"]=regime
        trend["headline"]={"偏多":"大盤偏多","偏空":"大盤偏空","整理":"大盤多空整理"}[regime]
        below=[name for n,name in ((20,"日20MA"),(100,"日100MA"),("week20","週20MA")) if not above[n]]
        trend["explanation"]=("收盤仍低於"+"、".join(below)+"。" if below else "收盤站上日20MA、100MA及週20MA。")
        if regime=="偏空" and above[5]:
            trend["explanation"]+="短線回穩，中期空頭結構尚未扭轉。"
            trend["short_headline"]="短線反彈"
        elif regime=="偏空":
            trend["explanation"]+="中期空頭結構尚未扭轉。"
        elif regime=="偏多":
            trend["explanation"]+="中期多方結構維持。"
        else:
            trend["explanation"]+="多空仍待確認。"
    else:
        trend["price_regime"]=None
        trend["headline"]="大盤價格趨勢待確認"
        trend["explanation"]="價格位置或均線資料待確認，暫不判定多空。"
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
    if report_at is not None and cbc_fx_rows is not None:
        comparison=compare_live_to_cbc_close(raw_fx,cbc_fx_rows,report_at)
        fx=values.get("usdtwd") or {}
        if comparison["status"]=="ok" and fx.get("status")=="live":
            fx["previous_close"]=f"{comparison['previous_close']:.3f}"
            fx["change"]=f"{comparison['usd_twd_change']:+.4f} ({comparison['usd_twd_change_percent']:+.2f}%) · "+("臺幣貶值" if comparison["direction"]=="TWD_depreciation" else "臺幣升值" if comparison["direction"]=="TWD_appreciation" else "持平")
            fx["timestamp"]+=f"｜對照央行 {comparison['previous_close_date']} 收盤（不同來源）"
        elif fx.get("status")=="live":
            fx["timestamp"]+="｜央行前收比較資料不足"
        fx_trend=fx_trend_snapshot(cbc_fx_rows,report_at.astimezone(TPE).date())
        ma5,ma20=fx_trend["daily_ma5"],fx_trend["daily_ma20"]
        if ma5 is not None and ma20 is not None:
            fx["trend"]=fx_trend
            values["usdtwd"]=fx
    if "taiex" not in values:
        target=Path(path) if path is not None else STORE
        rows=[r for r in read_store(target) if r["date"] < trend["as_of"]]
        if rows:
            current=rows[-1]
            change=None
            if len(rows)>=2:
                delta=current["close"]-rows[-2]["close"]
                change=f"{delta:+,.2f} ({delta/rows[-2]['close']:+.2%})"
            values["taiex"]={"value":f"{current['close']:,.2f}","change":change,"previous_close":f"{rows[-2]['close']:,.2f}" if len(rows)>=2 else None,
                             "timestamp":f"{current['date']} 收盤"}
    outlook, observation = market_outlook(trend, values)
    return build_premarket_flex(values,observed_at=datetime.fromisoformat(trend["as_of"]).strftime("%Y.%m.%d %a").upper()+" ｜ 08:55",trend=trend,system_status=system_status,
                                outlook=outlook,observation=observation)


def market_outlook(trend, values):
    """Use validated quote changes only; no weighted score or invented prices."""
    def direction(key):
        item=values.get(key) or {}
        if item.get("status") != ("close" if key=="sox" else "live"):
            return None
        try:
            change=float(str(item.get("change")).split()[0].replace(",","").replace("−","-").rstrip("%"))
            if not __import__("math").isfinite(change):
                return None
            return (change>0)-(change<0)
        except (ValueError, IndexError, TypeError):
            return None
    tx,sox,fx=(direction(k) for k in ("tx","sox","usdtwd"))
    weekly=trend.get("price_regime") if "price_regime" in trend else (trend.get("weekly") or {}).get("structure")
    daily=trend.get("price_regime") if "price_regime" in trend else (trend.get("daily") or {}).get("structure")
    labels={1:"上漲",-1:"下跌",0:"持平",None:"資料不足"}
    fx_labels={1:"貶值",-1:"升值",0:"持平",None:"資料不足"}
    observation=f"臺指期{labels[tx]}、費半{labels[sox]}、臺幣{fx_labels[fx]}。"
    if tx is None:
        title="今日方向待評估"
        observation+="缺少有效臺指期漲跌資料，暫不推估開盤方向。"
    elif tx==0:
        title="盤前方向中性"
        observation+="臺指期持平，開盤方向尚不明朗。"
    else:
        side="偏多" if tx>0 else "偏空"
        aligned=sox==tx and fx==-tx
        observation+=f"臺指期顯示開盤{side}傾向。"
        observation+=("費半與匯率方向一致。" if aligned else "輔助指標未完全確認，仍須觀察。")
        if weekly=="偏多":
            title=("多頭共振" if aligned and daily=="偏多" else "偏多但仍須觀察") if tx>0 else "多頭結構下的短線回檔"
        elif weekly=="偏空":
            title=("空頭共振" if aligned and daily=="偏空" else "偏空但仍須觀察") if tx<0 else "空頭結構下的短線反彈"
        elif weekly=="整理":
            title=f"整理格局，開盤{side}"
        else:
            title=f"開盤{side}，整體趨勢待確認"
    short=trend.get("short_term") or {}
    levels=short.get("levels") or {}
    if levels:
        observation+="\n短線攻防："+short["label"]+"。"
        if tx is not None and tx>0 and not levels[5]["above"] and not levels[10]["above"]:
            observation+="盤前偏多仍須觀察能否收復短期均線。"
        elif tx is not None and tx<0 and levels[5]["above"] and levels[10]["above"]:
            observation+="昨日短線仍偏多，今日留意均線支撐。"
    return title, observation.split("\n")[0]
