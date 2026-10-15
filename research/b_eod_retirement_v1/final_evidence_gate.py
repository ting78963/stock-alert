# -*- coding: utf-8 -*-
"""Offline EOD final-evidence gate. Research only; never contacts Fugle or LINE."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class FinalEvidence:
    date: str
    stock_id: str
    final_minute: str
    rest_last_minute: str
    canonical_last_minute: str
    completed_through: str
    rest_rows: int
    canonical_rows: int
    pending_line: bool
    queue_drained: bool
    worker_exited: bool
    evaluation_ok: bool

def check(e: FinalEvidence) -> tuple[bool, tuple[str,...]]:
    """A positive result still requires a trusted REST caller and persisted marker."""
    failed=[]
    if not (len(e.date)==10 and e.date[4]=="-" and e.date[7]=="-"): failed.append("date")
    if not (e.stock_id.isdigit() and len(e.stock_id)==4): failed.append("stock_id")
    if e.final_minute!="13:30:00": failed.append("unsupported_final_minute")
    if e.rest_last_minute!=e.final_minute: failed.append("rest_final_minute")
    if e.canonical_last_minute!=e.final_minute: failed.append("canonical_final_minute")
    if e.completed_through!=e.final_minute: failed.append("evaluation_through")
    if e.rest_rows<=0 or e.canonical_rows<=0: failed.append("empty_data")
    if e.rest_rows!=e.canonical_rows: failed.append("row_count_mismatch")
    if e.pending_line: failed.append("pending_line")
    if not e.queue_drained: failed.append("queue_not_drained")
    if not e.worker_exited: failed.append("worker_alive")
    if not e.evaluation_ok: failed.append("evaluation_failed")
    return not failed,tuple(failed)
