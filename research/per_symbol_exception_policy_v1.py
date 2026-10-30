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
