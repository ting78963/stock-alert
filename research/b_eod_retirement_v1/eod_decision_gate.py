# -*- coding: utf-8 -*-
"""B EOD research-only two-phase decision gate. No network, no side effects.

Close is allowed only after independently supplied evidence is verified.
REST bar equality alone never establishes REST finality.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class EODEvidence:
    admission_closed: bool
    queue_drained: bool
    worker_exited: bool
    rest_final_authoritative: bool
    rest_canonical_match: bool
    final_evaluation_ok: bool
    pending_line_count: int
    line_delivery_settled: bool
    session_day_verified: bool

GATES=("admission_closed","queue_drained","worker_exited",
       "rest_final_authoritative","rest_canonical_match",
       "final_evaluation_ok","line_delivery_settled","session_day_verified")

def decide_eod_retirement(e):
    if not isinstance(e,EODEvidence):raise TypeError("EODEvidence required")
    failed=[name for name in GATES if getattr(e,name) is not True]
    if type(e.pending_line_count) is not int or e.pending_line_count!=0:
        failed.append("pending_line_count")
    return {"retire":not failed,"hold_reasons":failed}
