# -*- coding: utf-8 -*-
"""Compatibility entrypoint. Render keeps its existing start command while production uses shared-WS v2."""
import threading
from production_worker_v2_shared_ws import main
from f15_eod_signal_report import loop as f15_eod_loop
from f15_uniform_history_backfill import run as f15_uniform_history_run
from f15_trajectory_store import loop as f15_trajectory_loop
from f15_research_export_once import loop_once as f15_research_export_once
from f15_research_reexport_v2 import loop_once as f15_research_reexport_v2
from a_queue_archive_maintenance_v1 import loop as queue_archive_loop

if __name__=="__main__":
    threading.Thread(target=queue_archive_loop,name="queue-archive-maintenance",daemon=True).start()
    threading.Thread(target=f15_eod_loop,name="f15-eod",daemon=True).start()
    threading.Thread(target=f15_uniform_history_run,name="f15-uniform-history",daemon=True).start()
    threading.Thread(target=f15_trajectory_loop,name="f15-trajectory",daemon=True).start()
    threading.Thread(target=f15_research_export_once,name="f15-research-export",daemon=True).start()
    threading.Thread(target=f15_research_reexport_v2,name="f15-research-reexport-v2",daemon=True).start()
    main()