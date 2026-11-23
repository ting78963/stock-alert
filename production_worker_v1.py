# -*- coding: utf-8 -*-
"""Compatibility entrypoint. Render keeps its existing start command while production uses shared-WS v2."""
import threading
from production_worker_v2_shared_ws import main
from f15_eod_signal_report import loop as f15_eod_loop
from market_data_maintenance_v1 import loop as market_data_loop
from usdtwd_cbc_maintenance_v1 import maintain_cbc_once
from datetime import datetime
from zoneinfo import ZoneInfo
import time

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
from f15_uniform_history_backfill import run as f15_uniform_history_run
from f15_trajectory_store import loop as f15_trajectory_loop
from f15_research_export_once import loop_once as f15_research_export_once
from f15_research_reexport_v2 import loop_once as f15_research_reexport_v2
from a_queue_archive_maintenance_v1 import loop as queue_archive_loop

if __name__=="__main__":
    threading.Thread(target=queue_archive_loop,name="queue-archive-maintenance",daemon=True).start()
    threading.Thread(target=f15_eod_loop,name="f15-eod",daemon=True).start()
    threading.Thread(target=market_data_loop,name="market-taiex",daemon=True).start()
    threading.Thread(target=market_fx_loop,name="market-cbc",daemon=True).start()
    threading.Thread(target=f15_uniform_history_run,name="f15-uniform-history",daemon=True).start()
    threading.Thread(target=f15_trajectory_loop,name="f15-trajectory",daemon=True).start()
    threading.Thread(target=f15_research_export_once,name="f15-research-export",daemon=True).start()
    threading.Thread(target=f15_research_reexport_v2,name="f15-research-reexport-v2",daemon=True).start()
    main()