# -*- coding: utf-8 -*-
"""Compatibility entrypoint. Render keeps its existing start command while production uses shared-WS v2."""
import threading
from production_worker_v2_shared_ws import main
from f15_eod_signal_report import loop as f15_eod_loop
from market_data_maintenance_v1 import loop as market_data_loop
from market_bootstrap_once_v1 import loop as market_bootstrap_loop
from usdtwd_cbc_maintenance_v1 import maintain_cbc_once
from market_maintenance_delivery_v1 import deliver_once
from market_line_sender_v1 import send_market_flex
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import os

def market_report_loop():
    tz = ZoneInfo('Asia/Taipei')
    while True:
        now = datetime.now(tz)
        if now.weekday() < 5 and 17 <= now.hour < 18:
            try:
                result = deliver_once(now, send_market_flex)
                if result not in ('not_due', 'already_sent', 'waiting_for_data'):
                    print(f'[MARKET LINE] {now.date()} {result}', flush=True)
            except Exception as exc:
                print(f'[MARKET LINE FAIL] {now.date()} {type(exc).__name__}: {exc}', flush=True)
        time.sleep(300)

def market_fx_loop():
    tz = ZoneInfo('Asia/Taipei')
    last_done = None
    while True:
        now = datetime.now(tz)
        day = now.date().isoformat()
        if now.weekday() < 5 and 17 <= now.hour < 18 and last_done != day:
            try:
                result = maintain_cbc_once(now)
                if result in ('updated', 'already_updated'):
                    last_done = day
                print(f'[MARKET CBC] {day} {result}', flush=True)
            except Exception as exc:
                print(f'[MARKET CBC FAIL] {day} {type(exc).__name__}: {exc}', flush=True)
        time.sleep(300)
def premarket_sox_loop():
    """Opt-in 08:54 prefetch / 08:55 delivery; separate from A/B."""
    from research.premarket_sox_delivery_v1 import deliver_premarket_once
    from research.premarket_sox_sender_v1 import send_premarket_flex
    from research.premarket_market_brief_v1 import build_market_brief
    from twse_session_gate_v1 import is_scheduled_open
    state='/var/data/stock-alert/market_data/premarket_sox_sent.json'
    tz=ZoneInfo('Asia/Taipei')
    prepared_day=None
    prepared_card=None
    open_day=None
    finished_day=None
    next_attempt=None
    while True:
        now=datetime.now(tz)
        if (now.weekday()<5 and now.hour==8 and 54<=now.minute<60
                and finished_day!=now.date()
                and (next_attempt is None or now>=next_attempt)):
            try:
                if prepared_day!=now.date():
                    from pathlib import Path
                    import json
                    marker=Path(state)
                    if marker.exists() and json.loads(marker.read_text(encoding='utf-8')).get('sent_date')==now.date().isoformat():
                        finished_day=now.date()
                        continue
                    prepared_card=None
                    open_day=is_scheduled_open(now.date())
                    if open_day:
                        prepared_card=build_market_brief(datetime.now(tz), clock=lambda: datetime.now(tz))
                    prepared_day=now.date()
                    if not open_day:
                        finished_day=now.date()
                now=datetime.now(tz)
                if open_day and prepared_card is not None and now.date()==prepared_day and now.hour==8 and 55<=now.minute<60:
                    result=deliver_premarket_once(now,send_premarket_flex,state,
                        card_builder=lambda _:prepared_card,session_gate=lambda day:day==prepared_day and open_day)
                    if result in ('sent','already_sent','market_closed'):
                        finished_day=now.date()
                    if result not in ('not_due','already_sent'):
                        print(f'[PREMARKET SOX] {now.date()} {result}',flush=True)
            except Exception as exc:
                from datetime import timedelta
                next_attempt=datetime.now(tz)+timedelta(seconds=20)
                print(f'[PREMARKET SOX FAIL] {now.date()} {type(exc).__name__}',flush=True)
        time.sleep(5 if now.hour==8 and 53<=now.minute<60 else 30)

from f15_uniform_history_backfill import run as f15_uniform_history_run
from f15_trajectory_store import loop as f15_trajectory_loop
from f15_research_export_once import loop_once as f15_research_export_once
from f15_research_reexport_v2 import loop_once as f15_research_reexport_v2
from a_queue_archive_maintenance_v1 import loop as queue_archive_loop

if __name__=="__main__":
    if os.getenv("PREMARKET_SOX_0855_ENABLED","0")=="1":
        threading.Thread(target=premarket_sox_loop,name="premarket-sox-0855",daemon=True).start()
    threading.Thread(target=queue_archive_loop,name="queue-archive-maintenance",daemon=True).start()
    threading.Thread(target=f15_eod_loop,name="f15-eod",daemon=True).start()
    threading.Thread(target=market_data_loop,name="market-taiex",daemon=True).start()
    threading.Thread(target=market_bootstrap_loop,name="market-history-bootstrap",daemon=True).start()
    threading.Thread(target=market_fx_loop,name="market-cbc",daemon=True).start()
    threading.Thread(target=market_report_loop,name="market-line-report",daemon=True).start()
    threading.Thread(target=f15_uniform_history_run,name="f15-uniform-history",daemon=True).start()
    threading.Thread(target=f15_trajectory_loop,name="f15-trajectory",daemon=True).start()
    threading.Thread(target=f15_research_export_once,name="f15-research-export",daemon=True).start()
    threading.Thread(target=f15_research_reexport_v2,name="f15-research-reexport-v2",daemon=True).start()
    main()