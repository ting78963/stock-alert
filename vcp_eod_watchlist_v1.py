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
    price_above_threshold = closes[-1] > threshold
    confirmed = bool(state.get("justBroke") and state.get("contracting"))
    track = selector.track.get(symbol, {})
    # A fresh isolated track cannot prove that today is a new event.
    # Replay prior sessions only for a candidate first-day breakout.
    if confirmed and state.get("breakDays") == 1:
        selector.track.clear()
        for end in range(max(30,len(closes)-10),len(closes)):
            selector.analyze_vcp(closes[:end],vols[:end],symbol,dates[:end])
        prior = selector.track.get(symbol, {})
        if prior and closes[-1] >= float(prior.get("pivot") or 0)*0.997:
            return None
        selector.track.clear()
        state = selector.analyze_vcp(closes,vols,symbol,dates)
        track = selector.track.get(symbol,{})
    if confirmed and state.get("breakDays") == 1 and track.get("breakoutDate") == dates[-1]:
        category = "first_breakout"
    elif state.get("status") == "final_contraction" and not confirmed:
        pivot_ref = float((state.get("breakoutTrack") or {}).get("pivot") or pivot or max(closes[-20:]))
        if not (pivot_ref > 0 and pivot_ref * 0.975 <= closes[-1] < pivot_ref):
            return None
        category = "near"
        pivot = max(closes[-20:])
        threshold = pivot * 1.003
    else:
        return None
    reference_price = max(closes[-20:]) * 1.005
    prior20 = [v for v in vols[-21:-1] if v > 0]
    full = math.floor(sum(prior20) / len(prior20) * 1.5 + 0.5)
    return {"reference_price": reference_price, "reference_distance": (reference_price / closes[-1] - 1) * 100,
            "volume_10": math.floor(full * 0.18 + 0.5), "volume_12": math.floor(full * 0.55 + 0.5),
            "volume_full": full, "volume_today": vols[-1], "symbol": symbol, "day": dates[-1], "category": category,
            "close": closes[-1], "pivot": pivot, "threshold": threshold,
            "distance_pct": (threshold / closes[-1] - 1) * 100,
            "price_above_threshold": price_above_threshold,
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
            if not isinstance(meta, dict) or str(meta.get("symbol") or symbol) != symbol:
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
    """White V4 brief as independent vertical messages."""
    import json
    def t(value, color="#202124", size="sm", align="start"):
        return {"type":"text","text":str(value),"color":color,"size":size,"weight":"bold","wrap":True,"align":align}
    def box(items, layout="vertical", **kw):
        return {"type":"box","layout":layout,"contents":items,**kw}
    def pair(a,b):
        return box([a,b],"horizontal",spacing="xs")
    def number(v):
        return f"{v:,.0f}"
    def price(v):
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    entries=[]
    for key,title,color in (("near","⚡ 即將突破","#B77922"),("first_breakout","🔥 首次突破","#A51C35")):
        rows=result[key]
        if not rows:
            entries.append((key,title,color,None))
        for row in rows:
            entries.append((key,title,color,row))
    pages=[entries[i:i+6] for i in range(0,len(entries),6)]
    # Each page is an independent LINE bubble.
    def bubble(page, index, total, omitted=0):
        body=[pair(t("↗ EVENING BRIEF","#A51C35"),t(f"{index:02d} / {total:02d}","#60646C","xs","end")),
              t("VCP 盤後簡報",size="xl"),t(result["day"]+"｜辨識完成","#60646C","xs")]
        last=None
        for key,title,color,row in page:
            if key!=last:
                body.extend([{"type":"separator","color":"#D5D7DA"},t(f"{title}｜{len(result[key])} 檔",color,"md")])
                last=key
            if row is None:
                body.append(t("無符合股票","#60646C"))
                continue
            if key=="near":
                items=[pair(t(f"{row['symbol']} {row['name']}"),t(f"差 {row['reference_distance']:.2f}%",color,"xs","end")),
                       pair(t(f"收盤 {price(row['close'])}","#50545A","xs"),t(f"突破價 {row['reference_price']:.1f}","#A51C35","xs","end")),
                       box([box([t(label,col,"xs"),t(number(row[field]),col,"sm")],flex=1) for label,field,col in
                            (("10:00 前","volume_10","#A51C35"),("12:00 前","volume_12","#B77922"),("全天門檻","volume_full","#202124"))],"horizontal",spacing="xs")]
            else:
                items=[pair(t(f"{row['symbol']} {row['name']}"),t(f"{row['volume_ratio']:.2f} 倍量",color,"xs","end")),
                       pair(t(f"收盤 {price(row['close'])}","#50545A","xs"),t(f"突破價 {price(row['threshold'])}",color,"xs","end")),
                       t(f"成交量 {number(row['volume_today'])} 張","#50545A","xs")]
            body.append(box(items,backgroundColor="#F3F4F6",cornerRadius="md",paddingAll="8px",spacing="xs"))
        if omitted:
            body.append(t(f"另有 {omitted} 檔未列出（LINE 容量限制）","#A51C35","xs"))
        body.extend([t("量能單位：張｜12:00 後謹慎觀察","#60646C","xs"),
                     t(f"有效辨識 {result['evaluated']}｜缺資料 {result['missing_metadata']+result['missing_history']}","#60646C","xs"),
                     t("Trade Smart | Your Edge","#60646C","xs","end")])
        return {"type":"bubble","size":"giga","body":box(body,backgroundColor="#FFFFFF",spacing="sm")}
    messages=[]
    for i,page in enumerate(pages):
        contents=bubble(page,i+1,len(pages))
        if len(json.dumps(contents,ensure_ascii=False,separators=(",",":")).encode())>29000:
            raise ValueError("LINE bubble exceeds safe size")
        messages.append({"type":"flex","altText":f"{result['day']} VCP 盤後簡報 {i+1}/{len(pages)}","contents":contents})
    return messages


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
    messages=build_flex(result)
    for offset in range(0,len(messages),5):
        retry=str(uuid.uuid5(uuid.NAMESPACE_URL,"vcp-eod-watchlist:"+result["day"]+":"+str(offset//5)))
        payload=json.dumps({"to":to,"messages":messages[offset:offset+5]},ensure_ascii=False).encode()
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


def main():
    import argparse, os
    from pathlib import Path
    from datetime import datetime
    from zoneinfo import ZoneInfo
    p=argparse.ArgumentParser()
    p.add_argument("--day",required=True)
    p.add_argument("--send",action="store_true")
    args=p.parse_args()
    now=datetime.now(ZoneInfo("Asia/Taipei"))
    if args.day!=now.date().isoformat() or (now.hour,now.minute)<(15,30):
        raise SystemExit("EOD current-day gate")
    root=Path("/var/data/stock-alert")
    marker=root/"vcp_eod_sent"/f"{args.day}.json"
    if args.send and marker.exists():
        return
    from vcp_scan_once_adapter import VcpScanOnceRuntime
    runtime=VcpScanOnceRuntime(lambda:now)
    result=scan_database(args.day,Path(os.getenv("A_SHARED_DAILY_DB",str(root/"shared_history_stage_v1.sqlite3"))),
                         root/"f10_baseline_v1.sqlite3",
                         root/"f11-staging/a_f11_staging_v1.json" if os.getenv("A_F11_OFFLINE_STAGING")=="1" else root/"a_f11_metadata_v1.json",
                         runtime.engine.selector)
    print(f"[VCP EOD] day={args.day} evaluated={result['evaluated']} near={len(result['near'])} first={len(result['first_breakout'])} missing_meta={result['missing_metadata']} missing_history={result['missing_history']}",flush=True)
    if args.send:
        send_once(result,marker)

if __name__=="__main__":
    main()
