"""Pure aggregation of already-completed B minute bars. No I/O."""
from math import isfinite

def partial_daily_candle(rows, day, cutoff=None):
    if not rows:
        return None
    try:
        bars = sorted(rows, key=lambda r: str(r["minute"])[:8])
        times = [str(r["minute"])[:8] for r in bars]
        if len(set(times)) != len(times):
            return None
        if any(str(r.get("date", day))[:10] != day for r in bars):
            return None
        if any(t < "09:00:00" or t > "13:30:00" for t in times):
            return None
        if cutoff is not None and any(t > str(cutoff)[:8] for t in times):
            return None
        values = []
        for bar in bars:
            o, h, l, c = (float(bar[k]) for k in ("open", "high", "low", "close"))
            if not all(isfinite(v) and v > 0 for v in (o, h, l, c)):
                return None
            if h < max(o, c) or l > min(o, c):
                return None
            values.append((o, h, l, c))
    except (KeyError, TypeError, ValueError):
        return None
    return {"date": day, "open": values[0][0],
            "high": max(v[1] for v in values),
            "low": min(v[2] for v in values),
            "close": values[-1][3]}

def append_partial_day(completed_days, minutes, day, cutoff=None):
    if any(str(r.get("date", "")) >= day for r in completed_days):
        return None
    candle = partial_daily_candle(minutes, day, cutoff)
    return [*completed_days, candle] if candle is not None else None
