# -*- coding: utf-8 -*-
"""Compatibility entrypoint. Render keeps its existing start command while production uses shared-WS v2."""
import threading
from production_worker_v2_shared_ws import main
from f15_eod_signal_report import loop as f15_eod_loop
from f15_uniform_history_backfill import run as f15_uniform_history_run
from f15_trajectory_store import loop as f15_trajectory_loop
from f15_research_export_once import loop_once as f15_research_export_once

if __name__=="__main__":
    threading.Thread(target=f15_eod_loop,name="f15-eod",daemon=True).start()
    threading.Thread(target=f15_uniform_history_run,name="f15-uniform-history",daemon=True).start()
    threading.Thread(target=f15_trajectory_loop,name="f15-trajectory",daemon=True).start()
    threading.Thread(target=f15_research_export_once,name="f15-research-export",daemon=True).start()
    main()
