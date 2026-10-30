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

def register_confirmed_halts_once(db_path, snapshot_day):
    """One-time operator-confirmed watch registration; never fake candles."""
    if str(snapshot_day)[:10] < "2026-10-30":
        return
    conn=sqlite3.connect(str(db_path),timeout=5)
    try:
        with conn:
            marker="operator_halts_20261030_v1"
            seen=conn.execute("SELECT 1 FROM suspension_meta WHERE key=?",(marker,)).fetchone()
            if seen:
                return
            members={row[0] for row in conn.execute("SELECT symbol FROM fetch_status")}
            confirmed={"5355","8176"}
            if not confirmed.issubset(members):
                raise AHistoryPreflightError("operator-confirmed symbols absent from history universe")
            from datetime import datetime,timezone
            now=datetime.now(timezone.utc).isoformat()
            for sym in sorted(confirmed):
                conn.execute("INSERT OR IGNORE INTO suspension_watch(symbol,confirmed_source,confirmed_at_utc) VALUES(?,?,?)",
                             (sym,"operator-confirmed-2026-10-30",now))
            conn.execute("INSERT INTO suspension_meta(key,value) VALUES(?,?)",(marker,now))
    finally:
        conn.close()

def verify_a_history(snapshot_day, db_path="/var/data/stock-alert/shared_history_stage_v1.sqlite3", rows=None):
    try:
        if rows is None: rows=fetch_schedule()
        required=last_completed_session(snapshot_day,rows)
        db=Path(db_path)
        if not db.is_file(): raise AHistoryPreflightError("shared daily SQLite missing")
        register_confirmed_halts_once(db,snapshot_day)
        conn=sqlite3.connect(f"file:{db}?mode=ro",uri=True,timeout=5)
        try:
            status=conn.execute("SELECT symbol,covered_through FROM fetch_status").fetchall()
            suspended={row[0] for row in conn.execute("SELECT symbol FROM suspension_watch")}
            quarantined={row[0] for row in conn.execute("SELECT symbol FROM fetch_error")}
            from research.per_symbol_exception_policy_v1 import check_systemic_health
            check_systemic_health(len(status),len(suspended | quarantined))
            count=conn.execute("SELECT COUNT(DISTINCT symbol) FROM daily_ohlcv").fetchone()[0]
        finally: conn.close()
        if not status: raise AHistoryPreflightError("fetch_status empty")
        bad=[s for s,covered in status if s not in suspended and s not in quarantined and (not covered or str(covered)[:10]<required)]
        if bad:
            from collections import Counter
            distribution=Counter(str(covered)[:10] if covered else "missing" for sym,covered in status if sym not in suspended and sym not in quarantined)
            raise AHistoryPreflightError(f"required={required} snapshot={snapshot_day} SQLite watermark incomplete count={len(bad)} coverage={dict(distribution.most_common(8))} sample={bad[:5]}")
        if count<len(status): raise AHistoryPreflightError(f"daily stock count {count} < status count {len(status)}")
        return required
    except AHistoryPreflightError: raise
    except Exception as exc:
        raise AHistoryPreflightError(f"calendar/database verification failed: {type(exc).__name__}: {exc}") from exc
