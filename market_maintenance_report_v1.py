# -*- coding: utf-8 -*-
"""Read-only combined maintenance report from actual persisted market data."""
from datetime import datetime
from zoneinfo import ZoneInfo
from taiex_fugle_store_v1 import read_store as read_taiex
from usdtwd_cbc_store_v1 import read_store as read_fx
from taiex_market_history_v1 import snapshot as taiex_snapshot
from usdtwd_cbc_daily_v1 import trend_snapshot as fx_snapshot
from market_maintenance_flex_v1 import build_market_maintenance_flex

TPE=ZoneInfo("Asia/Taipei")

def build_from_stores(now,taiex_path=None,fx_path=None):
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware report timestamp required")
    day=now.astimezone(TPE).date()
    report_as_of=day.isoformat()
    def get(read,path,snapshot,required):
        try:
            rows=read(path) if path is not None else read()
            latest=rows[-1]["date"] if rows else None
            # Snapshot excludes report day, so use next day for completed close.
            from datetime import timedelta
            state=snapshot(rows,(day+timedelta(days=1)).isoformat())
            enough=all(state.get(k) is not None for k in required)
            status="already_updated" if latest==report_as_of and enough else "incomplete"
            detail=f"資料日期：{latest or '無'}｜筆數：{len(rows)}"
            if not enough:
                detail+="｜均線歷史不足"
            return {"status":status,"latest":latest,"detail":detail}
        except Exception as exc:
            return {"status":"error","latest":None,"detail":f"讀取失敗：{type(exc).__name__}"}
    ta=get(read_taiex,taiex_path,taiex_snapshot,("daily_ma20","daily_ma100","weekly_ma20","weekly_ma100"))
    fx=get(read_fx,fx_path,fx_snapshot,("daily_ma5","daily_ma20"))
    return build_market_maintenance_flex(report_as_of,ta,fx)
