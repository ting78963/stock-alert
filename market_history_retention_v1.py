"""Bounded market history retention; preserve actual completed trading weeks."""
from datetime import date,timedelta
from taiex_market_history_v1 import normalize_daily

TAIEX_WEEKS=105
FX_DAYS=25

def retain_taiex(rows,as_of):
    rows=normalize_daily(rows)
    day=date.fromisoformat(str(as_of)[:10])
    monday=day-timedelta(days=day.weekday())
    cutoff=monday+timedelta(days=7) if day.weekday()>=5 else monday
    weeks=sorted({date.fromisoformat(r["date"])-timedelta(days=date.fromisoformat(r["date"]).weekday()) for r in rows if date.fromisoformat(r["date"])<cutoff})
    if len(weeks)<=TAIEX_WEEKS:return rows
    oldest=weeks[-TAIEX_WEEKS].isoformat()
    return [r for r in rows if r["date"]>=oldest]

def retain_fx(rows):
    return normalize_daily(rows)[-FX_DAYS:]
