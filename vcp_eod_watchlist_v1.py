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


def build_flex(result):
    """Bounded single-message report; show explicit overflow and coverage."""
    def t(value, color="#FFFFFF", size="sm"):
        return {"type":"text","text":str(value),"color":color,"size":size,"wrap":True}
    body=[t("VCP｜每日盤後觀察"," #FFFFFF".strip(),"lg"),
          t(result["day"],"#AAAAAA"),
          t(f"有效辨識 {result['evaluated']} 檔｜缺股票資料 {result['missing_metadata']}｜缺日K {result['missing_history']}","#AAAAAA","xs")]
    for key,title,color in (("near","即將突破","#FACC15"),("first_breakout","今日首次突破","#FF5555")):
        rows=result[key]
        body.extend([{"type":"separator","color":"#555555","margin":"md"},t(f"{title}｜{len(rows)} 檔",color,"md")])
        for row in rows[:15]:
            distance=row["distance_pct"]
            detail=(f"距門檻 {distance:.2f}%" if distance>=0 else "價格已越門檻，量能未確認") if key=="near" else f"量能 {row['volume_ratio']:.2f} 倍"
            body.append({"type":"box","layout":"vertical","margin":"sm","contents":[
                t(f"{row['symbol']} {row['name']}",color),
                t(f"收盤 {row['close']:.2f}｜門檻 {row['threshold']:.3f}","#DDDDDD","xs"),
                t(detail,"#AAAAAA","xs")]})
        if not rows: body.append(t("無符合股票","#AAAAAA"))
        if len(rows)>15: body.append(t(f"另有 {len(rows)-15} 檔未列出","#AAAAAA","xs"))
    return {"type":"flex","altText":f"{result['day']} VCP 盤後觀察｜即將突破 {len(result['near'])}｜首次突破 {len(result['first_breakout'])}",
            "contents":{"type":"bubble","size":"giga","body":{"type":"box","layout":"vertical","backgroundColor":"#080808","spacing":"sm","contents":body}}}


def send_once(result, marker):
    import json, os, uuid, urllib.request, urllib.error
    from pathlib import Path
    marker=Path(marker)
    if marker.exists():
        return False
    token=(os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_TOKEN") or "").strip()
    to=os.getenv("LINE_TO_ID","").strip()
    if not token or not to:
        raise RuntimeError("Recognition LINE credentials missing")
    retry=str(uuid.uuid5(uuid.NAMESPACE_URL,"vcp-eod-watchlist:"+result["day"]))
    payload=json.dumps({"to":to,"messages":[build_flex(result)]},ensure_ascii=False).encode()
    req=urllib.request.Request("https://api.line.me/v2/bot/message/push",data=payload,method="POST",
        headers={"Authorization":"Bearer "+token,"Content-Type":"application/json","X-Line-Retry-Key":retry})
    try:
        with urllib.request.urlopen(req,timeout=15) as response:
            if response.status!=200:
                raise RuntimeError("LINE push failed")
    except urllib.error.HTTPError as exc:
        if exc.code!=409 or not exc.headers.get("x-line-accepted-request-id"):
            raise
    marker.parent.mkdir(parents=True,exist_ok=True)
    tmp=marker.with_suffix(".tmp")
    tmp.write_text(json.dumps({"day":result["day"],"sent":True}),encoding="utf-8")
    tmp.replace(marker)
    return True
