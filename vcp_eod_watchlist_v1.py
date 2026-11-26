"""Read-only EOD VCP classification; no production track, network or handoff."""
import math

def classify(selector, symbol, bars):
    # Same minimum history as live A: 60 prior sessions plus current session.
    if len(bars) < 61:
        return None
    dates = [b[0] for b in bars]
    closes = [float(b[1]) for b in bars]
    vols = [float(b[2]) for b in bars]
    if dates != sorted(set(dates)) or not all(math.isfinite(x) and x > 0 for x in closes):
        return None
    if not all(math.isfinite(x) and x >= 0 for x in vols) or vols[-1] <= 0:
        return None
    if sum(vols[-6:-1]) <= 0:
        return None
    # Isolated selector: never read/write the live pivot track.
    selector.track.clear()
    state = selector.analyze_vcp(closes, vols, symbol, dates)
    pivot = float(state.get("pivot") or 0)
    if not math.isfinite(pivot) or pivot <= 0:
        return None
    threshold = pivot * 1.003
    confirmed = bool(state.get("justBroke") and state.get("contracting"))
    track = selector.track.get(symbol, {})
    if confirmed and state.get("breakDays") == 1 and track.get("breakoutDate") == dates[-1]:
        category = "first_breakout"
    elif state.get("status") == "final_contraction" and not confirmed:
        category = "near"
    else:
        return None
    return {"symbol": symbol, "day": dates[-1], "category": category,
            "close": closes[-1], "pivot": pivot, "threshold": threshold,
            "distance_pct": (threshold / closes[-1] - 1) * 100,
            "price_above_threshold": closes[-1] > threshold,
            "volume_ratio": vols[-1] / (sum(v for v in vols[-6:-1] if v > 0) /
                                        sum(v > 0 for v in vols[-6:-1]))}
