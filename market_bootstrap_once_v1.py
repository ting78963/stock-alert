# -*- coding: utf-8 -*-
"""One-time/resumable market history bootstrap on existing worker, outside trading hours."""
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TPE=ZoneInfo("Asia/Taipei")

def safe_to_bootstrap(now):
    local=now.astimezone(TPE)
    minute=local.hour*60+local.minute
    return local.weekday()>=5 or minute<510 or minute>=1200

def bootstrap_once(now):
    """One bounded Fugle request and one CBC historical download, only off-session."""
    if not safe_to_bootstrap(now):
        return "market_hours"
    from taiex_fugle_store_v1 import read_store, update
    from taiex_market_history_v1 import snapshot
    from usdtwd_cbc_store_v1 import read_store as read_fx, update as update_fx
    day=now.astimezone(TPE).date()
    # CBC official API returns full historical dataset in one request.
    fx=read_fx()
    if len(fx)<20 or fx[-1]["date"]<day.isoformat():
        result=update_fx(as_of=day)
        print(f"[MARKET BOOTSTRAP CBC] stored={result['stored']} latest={result['latest']}",flush=True)
    rows=read_store()
    state=snapshot(rows,(day+timedelta(days=1)).isoformat())
    if state["weekly_ma100"] is not None and state["daily_ma100"] is not None and rows and rows[-1]["date"]>=day.isoformat():
        return "complete"
    result=update(as_of=day,max_chunks=1)
    print(f"[MARKET BOOTSTRAP TAIEX] stored={result['stored']} latest={result['latest']} weekly_ma100_ready={result['snapshot']['weekly_ma100'] is not None}",flush=True)
    if result["snapshot"]["weekly_ma100"] is not None and result["snapshot"]["daily_ma100"] is not None:
        return "complete" if result["latest"]==day.isoformat() else "waiting_close"
    return "progress"

def loop():
    while True:
        now=datetime.now(TPE)
        if safe_to_bootstrap(now):
            try:
                status=bootstrap_once(now)
                if status in ("complete","waiting_close"):
                    print(f"[MARKET BOOTSTRAP] {status}; switching to scheduled maintenance",flush=True)
                    return
            except Exception as exc:
                print(f"[MARKET BOOTSTRAP FAIL] {type(exc).__name__}: {exc}",flush=True)
                # Retry later; do not affect A/B/F15 worker.
                time.sleep(900)
                continue
        time.sleep(30 if safe_to_bootstrap(now) else 300)
