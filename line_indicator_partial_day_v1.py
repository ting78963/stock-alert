"""Pure aggregation of completed minute bars for LINE indicator preview."""

def partial_daily_candle(rows, day):
    if not rows:
        return None
    bars = sorted(rows, key=lambda r: r['minute'])
    if any(str(r.get('date', day))[:10] != day for r in bars):
        return None
    for bar in bars:
        o, h, l, c = (float(bar[k]) for k in ('open', 'high', 'low', 'close'))
        if min(o, h, l, c) <= 0 or h < max(o, c) or l > min(o, c):
            return None
    return {'date': day, 'open': float(bars[0]['open']),
            'high': max(float(r['high']) for r in bars),
            'low': min(float(r['low']) for r in bars),
            'close': float(bars[-1]['close'])}
