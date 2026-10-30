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
