# -*- coding: utf-8 -*-
"""Small, isolated F15 TAIEX maintenance scheduler. No polling of market quotes."""
from datetime import datetime
from time import sleep
from zoneinfo import ZoneInfo
from taiex_twse_store_v1 import update
from twse_session_gate_v1 import is_scheduled_open

TPE = ZoneInfo("Asia/Taipei")


def should_run(now, last_success):
    """Run after 16:00 on weekdays; retry failed runs, once successful only once/day."""
    return now.weekday() < 5 and (now.hour, now.minute) >= (16, 0) and now.date().isoformat() != last_success


def loop():
    last_success = None
    while True:
        now = datetime.now(TPE)
        if should_run(now, last_success):
            if not is_scheduled_open(now.date()):
                sleep(1800)
                continue
            try:
                # TWSE index history is refreshed after the official close.
                result = update(as_of=now.date())
                if not result["latest"] or result["latest"] != now.date().isoformat():
                    raise RuntimeError(f"TAIEX official daily close not ready: {result['latest']}")
                last_success = now.date().isoformat()
                print(f"[F15 TAIEX UPDATED] {last_success} stored={result['stored']}", flush=True)
            except Exception as exc:
                print(f"[F15 TAIEX UPDATE FAIL] {now.date()} {type(exc).__name__}: {exc}", flush=True)
        sleep(1800)
