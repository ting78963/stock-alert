"""Pure per-symbol exception decisions. No production imports, DB writes or network.

The scanner must skip quarantined symbols BEFORE preflight can ignore them.
"""
from collections import Counter

class SystemicHistoryFailure(RuntimeError):
    pass

def classify_exception(symbol, error, previous=None):
    """Only record failures; never infer a trading halt from HTTP 404."""
    if not symbol or not error:
        raise ValueError("symbol and error required")
    return {"symbol": str(symbol), "state": "QUARANTINED",
            "reason": str(error), "previous": previous}

def should_scan(symbol, quarantined):
    """Normal stocks follow the unchanged scanning path."""
    return str(symbol) not in quarantined

def check_systemic_health(total, quarantined_count, max_fraction=0.05):
    """Fail closed on widespread missing data or empty universe."""
    if total <= 0 or quarantined_count < 0 or quarantined_count > total:
        raise SystemicHistoryFailure("invalid history universe")
    if quarantined_count / total > max_fraction:
        raise SystemicHistoryFailure("widespread history failure")
    return True

def recover(symbol, missing_sessions, verified_bars):
    """Recovery needs every missing session verified; no synthetic candles."""
    if not missing_sessions:
        return True
    return set(missing_sessions).issubset(set(verified_bars))

def read_quarantined(db_path):
    """Read only recorded single-stock fetch errors; never modify production DB."""
    import sqlite3
    from pathlib import Path
    path=Path(db_path)
    if not path.is_file():
        raise SystemicHistoryFailure("history database missing")
    try:
        with sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=3) as conn:
            return frozenset(str(row[0]) for row in conn.execute("SELECT symbol FROM fetch_error"))
    except sqlite3.Error as exc:
        raise SystemicHistoryFailure(f"history exception registry unavailable: {exc}") from exc

def verified_recovery(rows, start_day, end_day, required_sessions):
    """Verify every required market session has a valid bar; closures are excluded
    by the caller's official session calendar, not inferred from missing bars.
    """
    from datetime import date
    begin=date.fromisoformat(start_day)
    end=date.fromisoformat(end_day)
    if begin>end:
        return False
    expected={str(day) for day in required_sessions if start_day<=str(day)<=end_day}
    if not expected or end_day not in expected:
        return False
    available=set()
    for row in rows:
        day=str(row[0])
        if day not in expected:
            continue
        try:
            op,hi,lo,cl,vol=(float(x) for x in row[1:6])
        except (TypeError,ValueError):
            continue
        if min(op,hi,lo,cl)>0 and vol>=0 and hi>=max(op,cl,lo) and lo<=min(op,cl,hi):
            available.add(day)
    return expected.issubset(available)
