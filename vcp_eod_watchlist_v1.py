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


def scan_database(day, db_path, f10_path, metadata_path, selector):
    """Read one symbol at a time, using the same metadata and history gates."""
    import json
    import sqlite3
    from pathlib import Path
    from contextlib import closing
    from datetime import date, timedelta
    start = (date.fromisoformat(day) - timedelta(days=171)).isoformat()
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))["symbols"]
    if not isinstance(metadata, dict) or not metadata:
        raise ValueError("missing F11 metadata")
    def connect(path):
        return sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro", uri=True, timeout=5)
    result = {"day": day, "near": [], "first_breakout": [], "evaluated": 0,
              "excluded": 0, "missing_metadata": 0, "missing_history": 0}
    with closing(connect(db_path)) as db, closing(connect(f10_path)) as f10:
        members = f10.execute("SELECT symbol FROM member ORDER BY symbol")
        for (symbol,) in members:
            symbol = str(symbol)
            if not selector.basic_code_ok(symbol):
                result["excluded"] += 1
                continue
            meta = metadata.get(symbol)
            if not isinstance(meta, dict) or str(meta.get("symbol") or "") != symbol:
                result["missing_metadata"] += 1
                continue
            if not selector.meta_ok(meta):
                result["excluded"] += 1
                continue
            coverage = db.execute("SELECT covered_through FROM fetch_status WHERE symbol=?", (symbol,)).fetchone()
            if not coverage or str(coverage[0]) < day:
                result["missing_history"] += 1
                continue
            bars = db.execute("SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day>=? AND day<=? ORDER BY day",
                              (symbol,start,day)).fetchall()
            if len(bars) < 61 or bars[-1][0] != day or bars[-1][2] <= 0:
                result["missing_history"] += 1
                continue
            result["evaluated"] += 1
            row = classify(selector,symbol,bars)
            if row:
                row["name"] = str(meta.get("name") or symbol)
                result[row["category"]].append(row)
    if not result["evaluated"]:
        raise ValueError("no eligible current-day histories")
    result["near"].sort(key=lambda r: (abs(r["distance_pct"]),r["symbol"]))
    result["first_breakout"].sort(key=lambda r: (-r["volume_ratio"],r["symbol"]))
    return result
