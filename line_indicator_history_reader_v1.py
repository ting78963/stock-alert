"""Read-only historical daily candles, strictly earlier than signal day."""
import sqlite3
from pathlib import Path
from math import isfinite

DEFAULT_DB = "/var/data/stock-alert/shared_history_stage_v1.sqlite3"

def completed_daily_rows(symbol, day, db_path=DEFAULT_DB, limit=180):
    path = Path(db_path)
    if not path.is_file() or limit < 35:
        return None
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            records = db.execute(
                "SELECT day,open,high,low,close FROM daily_ohlcv "
                "WHERE symbol=? AND day<? ORDER BY day DESC LIMIT ?",
                (str(symbol), day, limit)).fetchall()
    except (sqlite3.Error, OSError, ValueError):
        return None
    if len(records) < 90:
        return None
    out = []
    for d, o, h, l, c in reversed(records):
        try:
            o, h, l, c = map(float, (o, h, l, c))
        except (TypeError, ValueError):
            return None
        if not all(isfinite(v) and v > 0 for v in (o, h, l, c)):
            return None
        if h < max(o, c) or l > min(o, c):
            return None
        out.append({"date": d, "open": o, "high": h, "low": l, "close": c})
    if any(out[i]["date"] >= out[i+1]["date"] for i in range(len(out)-1)):
        return None
    return out
