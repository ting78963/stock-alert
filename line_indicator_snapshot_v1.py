"""Assemble isolated LINE indicator values without changing B signal decisions."""
from line_indicator_history_reader_v1 import completed_daily_rows
from line_indicator_partial_day_v1 import append_partial_day
from line_indicator_calculations_v1 import macd, ma_cross_day, ma_prepare, weekly_kd_label, strong_buy

def compute_indicators(symbol, day, minute_rows, cutoff, db_path=None):
    kwargs = {} if db_path is None else {"db_path": db_path}
    history = completed_daily_rows(symbol, day, **kwargs)
    if history is None:
        return {}
    rows = append_partial_day(history, minute_rows, day, cutoff)
    if rows is None:
        return {}
    osc = macd([r["close"] for r in rows])
    current = osc["hist"]
    previous = osc["prev_hist"]
    # Website: prior close below prior MA20, live price above intraday MA20.
    # Snapshot has no browser localStorage, so this is the condition at signal time.
    prior_closes = [float(r["close"]) for r in history]
    live_close = float(rows[-1]["close"])
    ma20_first_above = (len(prior_closes) >= 20
                        and prior_closes[-1] < sum(prior_closes[-20:]) / 20
                        and live_close >= (sum(prior_closes[-19:]) + live_close) / 20)
    result = {
        "osc": current,
        "osc_delta": round(current - previous, 4) if current is not None and previous is not None else None,
        "weekly_kd": weekly_kd_label(rows),
        "ma_cross_day": ma_cross_day(rows),
        "ma_prepare": ma_prepare(rows),
        "strong_buy": strong_buy(history),
        "ma20_first_above": ma20_first_above,
    }
    return result
