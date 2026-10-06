# -*- coding: utf-8 -*-
from __future__ import annotations

import f15_research_export_once as export_v1
import f15_trajectory_store as ts

V1_MARK = export_v1.MARK
V2_MARK = ts.OUT / "_research_export_20260929_20261006_v2.done"


def loop_once():
    if V2_MARK.exists():
        print("[F15 RESEARCH REEXPORT V2] already_done", flush=True)
        return

    old_mark = export_v1.MARK
    try:
        export_v1.MARK = V2_MARK
        export_v1.run()
    finally:
        export_v1.MARK = old_mark
