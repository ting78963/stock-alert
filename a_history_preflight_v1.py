# -*- coding: utf-8 -*-
"""A preflight gate: one official calendar fetch, read-only DB coverage, fail closed."""
from datetime import date,timedelta
from pathlib import Path
import sqlite3
from twse_session_gate_v1 import fetch_schedule,is_scheduled_open,SessionGateError

class AHistoryPreflightError(RuntimeError): pass

def last_completed_session(snapshot_day, rows):
    d=date.fromisoformat(str(snapshot_day)[:10])-timedelta(days=1)
    for _ in range(16):
        if is_scheduled_open(d,rows=rows):
            return d.isoformat()
        d-=timedelta(days=1)
    raise AHistoryPreflightError("no verified previous session within 16 days")

def verify_a_history(snapshot_day, db_path="/var/data/stock-alert/shared_history_stage_v1.sqlite3", rows=None):
    try:
        if rows is None: rows=fetch_schedule()
        required=last_completed_session(snapshot_day,rows)
        db=Path(db_path)
        if not db.is_file(): raise AHistoryPreflightError("shared daily SQLite missing")
        conn=sqlite3.connect(f"file:{db}?mode=ro",uri=True,timeout=5)
        try:
            status=conn.execute("SELECT symbol,covered_through FROM fetch_status").fetchall()
            suspended={row[0] for row in conn.execute("SELECT symbol FROM suspension_watch")}
            count=conn.execute("SELECT COUNT(DISTINCT symbol) FROM daily_ohlcv").fetchone()[0]
        finally: conn.close()
        if not status: raise AHistoryPreflightError("fetch_status empty")
        bad=[s for s,covered in status if s not in suspended and (not covered or str(covered)[:10]<required)]
        if bad:
            from collections import Counter
            distribution=Counter(str(covered)[:10] if covered else "missing" for sym,covered in status if sym not in suspended)
            raise AHistoryPreflightError(f"required={required} snapshot={snapshot_day} SQLite watermark incomplete count={len(bad)} coverage={dict(distribution.most_common(8))} sample={bad[:5]}")
        if count<len(status): raise AHistoryPreflightError(f"daily stock count {count} < status count {len(status)}")
        return required
    except AHistoryPreflightError: raise
    except Exception as exc:
        raise AHistoryPreflightError(f"calendar/database verification failed: {type(exc).__name__}: {exc}") from exc
