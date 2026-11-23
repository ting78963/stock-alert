# -*- coding: utf-8 -*-
"""Independent TAIEX market-data maintenance; scheduled by existing worker, not F15."""
from datetime import datetime
from zoneinfo import ZoneInfo
TPE=ZoneInfo('Asia/Taipei')

def maintain_taiex_once(now):
 # Independent market history maintenance; no F15 stock report dependency.
 from taiex_fugle_store_v1 import update, read_store
 if (now.hour, now.minute) < (14, 30) or now.weekday() >= 5:
  return "not_due"
 day = now.date().isoformat()
 rows = read_store()
 if rows and rows[-1]["date"] == day:
  from taiex_market_history_v1 import snapshot
  from datetime import timedelta as _timedelta
  s=snapshot(rows,(now.date()+_timedelta(days=1)).isoformat())
  if s["weekly_ma100"] is not None and s["daily_ma100"] is not None:
   return "already_updated"
  print(f"[MARKET TAIEX BOOTSTRAP] {day} current candle cached; continuing history repair",flush=True)
 from twse_session_gate_v1 import is_scheduled_open
 if not is_scheduled_open(now.date()):
  return "market_closed"
 result = update(as_of=now.date())
 if result["latest"] != day:
  if result["snapshot"]["weekly_ma100"] is None:
   print(f"[MARKET TAIEX BOOTSTRAP] {day} stored={result['stored']} latest={result['latest']}",flush=True)
   return "bootstrapping"
  raise RuntimeError(f"TAIEX official close not ready: {result['latest']}")
 if result["snapshot"]["weekly_ma100"] is None or result["snapshot"]["daily_ma100"] is None:
  raise RuntimeError("TAIEX history insufficient for MA100")
 print(f"[MARKET TAIEX UPDATED] {day} stored={result['stored']}",flush=True)
 return "updated"


def loop():
    import time
    last_day = None
    next_minute = 0
    finished_day = None
    while True:
        now = datetime.now(TPE)
        day = now.date().isoformat()
        if day != last_day:
            last_day = day
            next_minute = 0
        minute = now.hour * 60 + now.minute
        if minute >= 870 and minute >= next_minute and finished_day != day:
            next_minute = minute + 30
            try:
                outcome = maintain_taiex_once(now)
                if outcome in ("updated", "already_updated", "market_closed"):
                    finished_day = day
                    print(f"[MARKET TAIEX DAILY DONE] {day} {outcome}", flush=True)
            except Exception as exc:
                print(f'[MARKET TAIEX FAIL] {day} {type(exc).__name__}: {exc}', flush=True)
        time.sleep(300)
