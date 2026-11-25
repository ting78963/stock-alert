# -*- coding: utf-8 -*-
"""Persistent CBC USD/TWD daily closes. Read-only preview never fetches network data."""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from usdtwd_cbc_daily_v1 import fetch_daily, trend_snapshot
from market_history_retention_v1 import retain_fx, FX_DAYS

TPE=ZoneInfo("Asia/Taipei")
STORE=Path(os.getenv("USDTWD_CBC_HISTORY_PATH","/var/data/stock-alert/market_data/usdtwd_cbc_daily.json"))

def read_store(path=STORE):
    if not path.exists():
        return []
    obj=json.loads(path.read_text(encoding="utf-8"))
    if obj.get("schema")!="usdtwd_cbc_daily_v1" or not isinstance(obj.get("rows"),list):
        raise ValueError("CBC cache schema mismatch")
    from taiex_market_history_v1 import normalize_daily
    return normalize_daily(obj["rows"])

def update(as_of=None,path=STORE,session=None):
    """One official daily download per invocation; write only after successful parsing."""
    today=as_of or datetime.now(TPE).date()
    rows=fetch_daily(session=session)
    from taiex_market_history_v1 import normalize_daily
    rows=normalize_daily(rows)
    if not rows:
        raise ValueError("CBC returned empty daily history")
    if rows[-1]["date"]>str(today)[:10]:
        raise ValueError("CBC returned future close")
    old=read_store(path)
    if old and (len(rows)<min(len(old), FX_DAYS) or rows[-1]["date"]<old[-1]["date"]):
        raise ValueError("CBC historical data regressed; preserving old cache")
    rows=retain_fx(rows)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    try:
        tmp.write_text(json.dumps({"schema":"usdtwd_cbc_daily_v1","rows":rows},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return {"stored":len(rows),"latest":rows[-1]["date"],"snapshot":trend_snapshot(rows,today)}

if __name__=="__main__":
    print(json.dumps(update(),ensure_ascii=False,default=str))
