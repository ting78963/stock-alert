# -*- coding: utf-8 -*-
"""Compatibility entrypoint. Render keeps its existing start command while production uses shared-WS v2."""
import threading
from production_worker_v2_shared_ws import main
from f15_eod_signal_report import loop as f15_eod_loop

if __name__=="__main__":
    threading.Thread(target=f15_eod_loop,name="f15-eod",daemon=True).start()
    main()
