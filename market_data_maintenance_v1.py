# -*- coding: utf-8 -*-
"""Low-priority, bounded TAIEX maintenance; never runs during stock market hours."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TPE = ZoneInfo("Asia/Taipei")

def maintain_taiex_once(now):
    from taiex_fugle_store_v1 import update, read_store
    from taiex_market_history_v1 import snapshot
    from twse_session_gate_v1 import is_scheduled_open
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")
    local = now.astimezone(TPE)
    minute = local.hour * 60 + local.minute
    # Initial backfill may continue after the close, but NEVER during the opening session.
    if local.weekday() >= 5 or not (870 <= minute < 1200):
        return "not_due"
    if not is_scheduled_open(local.date()):
        return "market_closed"
    day = local.date().isoformat()
    rows = read_store()
    if rows and rows[-1]["date"] == day:
        state = snapshot(rows, (local.date() + timedelta(days=1)).isoformat())
        if state["weekly_ma100"] is not None and state["daily_ma100"] is not None:
            return "already_updated"
    result = update(as_of=local.date(), max_chunks=1)
    if result["latest"] != day:
        if result["snapshot"]["weekly_ma100"] is None:
            print(f"[MARKET TAIEX BOOTSTRAP] {day} stored={result['stored']} latest={result['latest']}", flush=True)
            return "bootstrapping"
        return "close_not_published"
    if result["snapshot"]["weekly_ma100"] is None or result["snapshot"]["daily_ma100"] is None:
        return "bootstrapping"
    print(f"[MARKET TAIEX UPDATED] {day} stored={result['stored']}", flush=True)
    return "updated"

def loop():
    import time
    finished_day = None
    while True:
        now = datetime.now(TPE)
        day = now.date().isoformat()
        minute = now.hour * 60 + now.minute
        if 870 <= minute < 1200 and finished_day != day:
            try:
                outcome = maintain_taiex_once(now)
                if outcome in ("updated", "already_updated", "market_closed"):
                    finished_day = day
                    print(f"[MARKET TAIEX DAILY DONE] {day} {outcome}", flush=True)
            except Exception as exc:
                print(f"[MARKET TAIEX FAIL] {day} {type(exc).__name__}: {exc}", flush=True)
        # At most one bounded API chunk per 5 minutes; no work during 09:00-13:30.
        time.sleep(300)
