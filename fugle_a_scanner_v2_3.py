#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fugle_a_scanner_v2_3.py

A = 自動強勢選股掃描器（不做 P1/A/B/C 辨識）
------------------------------------------------
正式目標：
Fugle Snapshot -> 原 index(4).html 強勢選股核心 -> 第一次發現 -> Bridge -> B

設計原則：
1) 不修改原強勢選股網站。
2) Snapshot 預設每 5 秒掃一次。
3) 同股同日只 handoff 一次。
4) 歷史日 K / ticker metadata 快取，不會每 5 秒重抓。
5) A 只發現；B 才辨識 P1/A/B/C。
6) API / 欄位 / 日期 audit 失敗時 FAIL CLOSED：
   AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL
7) 所有輸出只寫到 _production_output/fugle_a_scanner_v2。

原網站核心（index(4).html）：
- 上漲
- 累計成交額 >= 50,000,000
- 累計成交量 >= 4,000 張
- VR5 >= 1.5（前 5 個完整交易日日均量）
- VCP 有訊號：直接入選
- 無 VCP：漲幅 >= 3% 且 price >= MA20 才入選
- VCP breakout track：pivot、量能 1.4x、10 交易日追蹤、0.997 跌破失效

Fugle v1.0 mapping：
- symbol -> stock_id
- changePercent -> change_rate（百分比數值，例如 3.21，不再乘 100）
- tradeValue -> total_amount（元）
- tradeVolume -> total_volume（整股 Snapshot 為張）
- closePrice -> close
- Snapshot date -> date
- historical D volume 為股，因此 /1000 -> 張
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
BASE = "https://api.fugle.tw/marketdata/v1.0/stock"
OUTDIR = Path(__file__).resolve().parent / "_production_output" / "fugle_a_scanner_v2"
STATE_FILE = OUTDIR / "state.json"
TRACK_FILE = OUTDIR / "vcp_breakout_track_v2.json"
CACHE_FILE = OUTDIR / "cache.json"

# 對應原網站 excludedKeywords：
# 食品工業、造紙工業、建材營造、航運、觀光餐旅、金融保險、
# 貿易百貨、文化創意、生技醫療
EXCLUDED_INDUSTRY_CODES = {"02", "09", "14", "15", "16", "17", "18", "22", "32"}

ESTIMATED_VR5_MIN = 1.5
SCAN_INTERVAL_DEFAULT = 5.0
OPEN_HM = (9, 0)
CLOSE_HM = (13, 30)


class AuditStop(RuntimeError):
    pass


def now_tw() -> datetime:
    return datetime.now(TZ)


def iso_now() -> str:
    return now_tw().isoformat(timespec="seconds")


def ensure_outdir() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json_atomic(path: Path, obj: Any) -> None:
    ensure_outdir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_event(obj: Dict[str, Any]) -> None:
    ensure_outdir()
    p = OUTDIR / "events.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def http_json(url: str, api_key: Optional[str] = None, timeout: int = 15) -> Dict[str, Any]:
    headers = {"User-Agent": "fugle-a-scanner-v2.3/1.0"}
    if api_key:
        headers["X-API-KEY"] = api_key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise AuditStop(f"Fugle HTTP {e.code}: {body}") from e
    except Exception as e:
        raise AuditStop(f"Fugle request failed: {type(e).__name__}: {e}") from e


def fugle_key() -> str:
    key = os.environ.get("FUGLE_API_KEY", "").strip()
    if key:
        return key

    # 僅為相容使用者既有本機測試檔；不輸出 key。
    candidate = Path.home() / "Desktop" / "新增資料夾" / "Fugle_live_KBar_test_ready.py"
    if candidate.exists():
        txt = candidate.read_text(encoding="utf-8", errors="ignore")
        patterns = [
            r'FUGLE_API_KEY\s*=\s*["\']([^"\']+)["\']',
            r'api_key\s*=\s*["\']([^"\']+)["\']',
            r'API_KEY\s*=\s*["\']([^"\']+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, txt)
            if m and m.group(1).strip():
                return m.group(1).strip()
    raise AuditStop("FUGLE_API_KEY not found")


def is_market_window(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    hm = (dt.hour, dt.minute)
    return hm >= OPEN_HM and hm < CLOSE_HM


def sd_of(arr: List[float]) -> float:
    # 原 JS：population SD，分母 n
    if len(arr) < 2:
        return 0.0
    m = sum(arr) / len(arr)
    return math.sqrt(sum((x - m) ** 2 for x in arr) / len(arr))


def safe_max(arr: List[float]) -> float:
    # JS 的 Math.max(...[]) = -Infinity；正常 VCP path 不應落到空陣列。
    return max(arr) if arr else float("-inf")


@dataclass
class DailyBar:
    date: str
    close: float
    volume_zhang: float


class FugleAdapter:
    def __init__(self, key: str):
        self.key = key
        self.meta_cache: Dict[str, Dict[str, Any]] = {}
        self.daily_cache: Dict[str, Tuple[str, List[DailyBar]]] = {}

    def snapshot(self) -> List[Dict[str, Any]]:
        # COMMONSTOCK 直接排除 ETF / 特別股；TSE + OTC。
        out: List[Dict[str, Any]] = []
        envelope_dates = set()
        for market in ("TSE", "OTC"):
            q = urllib.parse.urlencode({"type": "COMMONSTOCK"})
            d = http_json(f"{BASE}/snapshot/quotes/{market}?{q}", self.key)
            snap_date = str(d.get("date") or "")[:10]
            if not snap_date:
                raise AuditStop(f"{market} Snapshot missing date")
            envelope_dates.add(snap_date)
            rows = d.get("data")
            if not isinstance(rows, list):
                raise AuditStop(f"{market} Snapshot missing data[]")
            for r in rows:
                try:
                    symbol = str(r["symbol"])
                    out.append({
                        "stock_id": symbol,
                        "name": str(r.get("name") or symbol),
                        "change_rate": float(r.get("changePercent") or 0.0),
                        "total_amount": float(r.get("tradeValue") or 0.0),
                        "total_volume": float(r.get("tradeVolume") or 0.0),  # 張
                        "close": float(r.get("closePrice") or 0.0),
                        "date": snap_date,
                        "market": market,
                    })
                except Exception:
                    continue

        if len(envelope_dates) != 1:
            raise AuditStop(f"Snapshot TSE/OTC date mismatch: {sorted(envelope_dates)}")
        return out

    def ticker(self, symbol: str) -> Dict[str, Any]:
        if symbol in self.meta_cache:
            return self.meta_cache[symbol]
        d = http_json(f"{BASE}/intraday/ticker/{urllib.parse.quote(symbol)}", self.key)
        if str(d.get("symbol") or "") != symbol:
            raise AuditStop(f"ticker identity mismatch: requested={symbol}, got={d.get('symbol')}")
        self.meta_cache[symbol] = d
        return d

    def daily_history(self, symbol: str, snapshot_date: str) -> List[DailyBar]:
        # 必須嚴格只用 snapshot_date 之前的完整交易日。
        cache_key = f"{symbol}|{snapshot_date}"
        if symbol in self.daily_cache and self.daily_cache[symbol][0] == cache_key:
            return self.daily_cache[symbol][1]

        to_d = date.fromisoformat(snapshot_date) - timedelta(days=1)
        from_d = to_d - timedelta(days=170)  # 約 5.5 月，足夠 >=60 交易日
        params = urllib.parse.urlencode({
            "from": from_d.isoformat(),
            "to": to_d.isoformat(),
            "timeframe": "D",
            "fields": "close,volume",
            "sort": "asc",
        })
        d = http_json(
            f"{BASE}/historical/candles/{urllib.parse.quote(symbol)}?{params}",
            self.key,
        )
        if str(d.get("symbol") or "") != symbol:
            raise AuditStop(f"history identity mismatch: requested={symbol}, got={d.get('symbol')}")
        rows = d.get("data")
        if not isinstance(rows, list):
            raise AuditStop(f"{symbol} historical candles missing data[]")

        bars: List[DailyBar] = []
        for r in rows:
            ds = str(r.get("date") or "")[:10]
            if not ds or ds >= snapshot_date:
                continue
            try:
                close = float(r["close"])
                # Fugle historical D 整股 volume 官方定義為「股」。
                vol_zhang = float(r["volume"]) / 1000.0
            except Exception:
                continue
            if close > 0:
                bars.append(DailyBar(ds, close, vol_zhang))
        bars.sort(key=lambda x: x.date)

        # 防止 API 意外混入當日/未來。
        if any(b.date >= snapshot_date for b in bars):
            raise AuditStop(f"{symbol} causal history audit failed")
        self.daily_cache[symbol] = (cache_key, bars)
        return bars

    def estimated_vr5_parts(self, symbol: str, snapshot_date: str, now_dt: datetime) -> Tuple[float, float, int]:
        """Fugle-only F10(t) + prior5 average, all from historical 1m volume."""
        cache_key = f"estvr5|{symbol}|{snapshot_date}"
        if not hasattr(self, "_estvr5_cache"):
            self._estvr5_cache = {}
        days = self._estvr5_cache.get(cache_key)
        if days is None:
            bars = self.daily_history(symbol, snapshot_date)
            hist_dates = [b.date for b in bars[-10:]]
            if len(hist_dates) < 5:
                raise AuditStop(f"{symbol} Estimated VR5 history <5 sessions")
            days = []
            for ds in hist_dates:
                q = urllib.parse.urlencode({
                    "timeframe": "1", "from": ds, "to": ds,
                    "fields": "open,high,low,close,volume,average", "sort": "asc",
                })
                o = http_json(f"{BASE}/historical/candles/{urllib.parse.quote(symbol)}?{q}", self.key)
                if str(o.get("symbol") or "") != symbol or str(o.get("timeframe") or "") != "1":
                    raise AuditStop(f"{symbol} Fugle 1m identity failed: {ds}")
                rows = o.get("data")
                if not isinstance(rows, list) or not rows:
                    raise AuditStop(f"{symbol} Fugle 1m empty: {ds}")
                full = 0.0
                pts = []
                seen = set()
                for x in rows:
                    raw_dt = str(x.get("date") or "")
                    if len(raw_dt) < 16:
                        continue
                    row_ds = raw_dt[:10]
                    if row_ds != ds:
                        raise AuditStop(f"{symbol} Fugle 1m date leakage: {row_ds} != {ds}")
                    tm = raw_dt[11:19]
                    if tm in seen:
                        raise AuditStop(f"{symbol} Fugle 1m duplicate minute: {ds} {tm}")
                    seen.add(tm)
                    v = float(x.get("volume") or 0.0)
                    if v < 0:
                        raise AuditStop(f"{symbol} Fugle 1m negative volume: {ds} {tm}")
                    full += v
                    pts.append((tm, full))
                if full > 0 and pts:
                    days.append({"date": ds, "full": full, "pts": pts})
            if len(days) < 5:
                raise AuditStop(f"{symbol} Estimated VR5 valid Fugle sessions <5")
            self._estvr5_cache[cache_key] = days

        cutoff = now_dt.strftime("%H:%M:00")
        fractions = []
        fulls = []
        for d in days:
            full = float(d["full"])
            cum = 0.0
            for tm, running in d["pts"]:
                if tm <= cutoff:
                    cum = float(running)
                else:
                    break
            fractions.append(cum / full)
            fulls.append(full)
        if len(fractions) < 5:
            raise AuditStop(f"{symbol} Estimated VR5 F10 valid days <5")
        f10 = sum(fractions) / len(fractions)
        avg5 = sum(fulls[-5:]) / len(fulls[-5:])
        if not math.isfinite(f10) or f10 <= 0 or avg5 <= 0:
            raise AuditStop(f"{symbol} invalid Estimated VR5 F10/avg5")
        return f10, avg5, len(fractions)


class StrongSelector:
    def __init__(self, track_path: Optional[Path] = TRACK_FILE):
        self.track_path = track_path
        self.track: Dict[str, Dict[str, Any]] = load_json(track_path, {}) if track_path else {}

    @staticmethod
    def basic_code_ok(symbol: str) -> bool:
        # 原網站：排除 00 開頭、非四位數。
        return bool(symbol and not symbol.startswith("00") and re.fullmatch(r"\d{4}", symbol))

    @staticmethod
    def meta_ok(meta: Dict[str, Any]) -> bool:
        # Fugle COMMONSTOCK 已先排 ETF/特別股；這裡再 fail-closed。
        if str(meta.get("market") or "") == "ESB":
            return False
        sec = str(meta.get("securityType") or "")
        if sec and sec != "01":  # 01 = 一般股票
            return False
        industry = str(meta.get("industry") or "")
        if industry in EXCLUDED_INDUSTRY_CODES:
            return False
        return True

    def analyze_vcp(
        self, closes: List[float], vols: List[float], stock_code: str, dates: List[str]
    ) -> Dict[str, Any]:
        # Python port of index(4).html analyzeVCP.
        n = len(closes)
        if n < 30:
            return {
                "status": "data_insufficient", "s1": 0, "s2": 0, "s3": 0,
                "contracting": False, "volDry": False,
                "pivot": closes[-1] if closes else 0,
                "justBroke": False, "breakDays": 0, "breakoutTrack": None,
            }

        s1 = sd_of(closes[-60:-40])
        s2 = sd_of(closes[-40:-20])
        s3 = sd_of(closes[-20:])
        prev20_high = safe_max(closes[-21:-1])
        cur = closes[-1]
        price_broke = cur > prev20_high * 1.003

        pre_break = [v for v in vols[-6:-1] if v > 0]
        avg_before = sum(pre_break) / len(pre_break) if pre_break else 0
        today_vol = vols[-1] if vols else 0
        vol_confirmed = today_vol >= avg_before * 1.4 if avg_before > 0 else False
        just_broke = price_broke and vol_confirmed

        break_days = 0
        if just_broke:
            for i in range(n - 1, max(-1, n - 11), -1):
                prior = closes[max(0, i - 20):i]
                if prior and closes[i] > max(prior) * 1.003:
                    break_days += 1
                else:
                    break

        vp1 = [v for v in vols[-60:-40] if v > 0]
        vp3 = [v for v in vols[-20:] if v > 0]
        ap1 = sum(vp1) / max(len(vp1), 1)
        ap3 = sum(vp3) / max(len(vp3), 1)
        vol_dry = ap3 < ap1 * 0.75

        valid = s1 > s2 and s2 > s3
        if just_broke and valid and break_days <= 5:
            status = "just_broke"
        elif just_broke and valid and break_days <= 15:
            status = "trending_up"
        elif just_broke and not valid:
            status = "not_formed"
        elif valid and s3 < s1 * 0.4:
            status = "final_contraction"
        elif valid:
            status = "contracting"
        elif s1 > s2 and s3 > s2 * 1.2:
            status = "broken_contraction"
        else:
            status = "not_formed"

        contracting = status in {"contracting", "final_contraction", "just_broke", "trending_up"}
        breakout_track = None

        if stock_code and dates and len(dates) == n:
            today = dates[-1]
            existing = self.track.get(stock_code)

            if just_broke and valid and break_days <= 2 and (
                not existing or existing.get("pivot") != prev20_high
            ):
                self.track[stock_code] = {
                    "pivot": prev20_high,
                    "breakoutDate": today,
                    "highSinceBreak": cur,
                }
                breakout_track = {
                    "dayCount": 1, "pivot": prev20_high, "isNew": True, "broken": False
                }

            elif existing:
                try:
                    break_idx = dates.index(existing["breakoutDate"])
                except (ValueError, KeyError):
                    break_idx = -1
                day_count = n - 1 - break_idx + 1 if break_idx >= 0 else None

                if day_count is not None and 1 <= day_count <= 10:
                    if cur > float(existing.get("highSinceBreak", cur)):
                        existing["highSinceBreak"] = cur
                        self.track[stock_code] = existing

                    if cur < float(existing["pivot"]) * 0.997:
                        self.track.pop(stock_code, None)
                        breakout_track = {
                            "dayCount": day_count,
                            "pivot": existing["pivot"],
                            "broken": True,
                        }
                    else:
                        breakout_track = {
                            "dayCount": day_count,
                            "pivot": existing["pivot"],
                            "highSinceBreak": existing.get("highSinceBreak", cur),
                            "broken": False,
                        }
                else:
                    self.track.pop(stock_code, None)

            else:
                # 原 JS：從昨天往回最多 10 個交易日做 retro breakout scan。
                for back in range(1, 11):
                    idx = n - 1 - back
                    if idx < 20:
                        break
                    hist_closes = closes[:idx + 1]
                    hist_prev20 = safe_max(hist_closes[-21:-1])
                    hist_cur = hist_closes[-1]
                    hist_price_broke = hist_cur > hist_prev20 * 1.003
                    hist_pre = [v for v in vols[max(0, idx - 5):idx] if v > 0]
                    hist_avg = sum(hist_pre) / len(hist_pre) if hist_pre else 0
                    hist_today_vol = vols[idx] if idx < len(vols) else 0
                    hist_vol_ok = hist_today_vol >= hist_avg * 1.4 if hist_avg > 0 else False

                    if hist_price_broke and hist_vol_ok:
                        hist_break_days = 0
                        for i in range(idx, max(-1, idx - 11), -1):
                            prior = closes[max(0, i - 20):i]
                            if prior and closes[i] > max(prior) * 1.003:
                                hist_break_days += 1
                            else:
                                break
                        if hist_break_days <= 2:
                            broken_since = any(
                                closes[i] < hist_prev20 * 0.997
                                for i in range(idx + 1, n)
                            )
                            if not broken_since:
                                day_count = n - 1 - idx + 1
                                if day_count <= 10:
                                    high_since = max(closes[idx:])
                                    self.track[stock_code] = {
                                        "pivot": hist_prev20,
                                        "breakoutDate": dates[idx],
                                        "highSinceBreak": high_since,
                                    }
                                    breakout_track = {
                                        "dayCount": day_count,
                                        "pivot": hist_prev20,
                                        "highSinceBreak": high_since,
                                        "broken": False,
                                        "retro": True,
                                    }
                                break

            if self.track_path:
                save_json_atomic(self.track_path, self.track)

        return {
            "status": status, "s1": s1, "s2": s2, "s3": s3,
            "contracting": contracting, "volDry": vol_dry,
            "pivot": prev20_high, "justBroke": just_broke,
            "breakDays": break_days, "breakoutTrack": breakout_track,
        }

    def select_one(
        self,
        stock: Dict[str, Any],
        meta: Dict[str, Any],
        bars: List[DailyBar],
        inject_snapshot_today: bool = True,
    ) -> Optional[Dict[str, Any]]:
        symbol = stock["stock_id"]

        if not self.basic_code_ok(symbol):
            return None
        if not self.meta_ok(meta):
            return None
        if float(stock.get("change_rate") or 0) <= 0:
            return None
        if len(bars) < 5:
            return None

        today_vol = float(stock.get("total_volume") or 0)
        vol_ratio = float(stock.get("_estimated_vr5") or 0.0)
        if vol_ratio < ESTIMATED_VR5_MIN:
            return None

        closes = [b.close for b in bars]
        vols = [b.volume_zhang for b in bars]
        dates = [b.date for b in bars]

        snap_date = str(stock.get("date") or "")[:10]
        if inject_snapshot_today and snap_date:
            # bars 嚴格只到 D-1，因此把盤中 close / 累計量當作今天這一根。
            closes.append(float(stock.get("close") or 0))
            vols.append(today_vol)
            dates.append(snap_date)

        vcp = self.analyze_vcp(closes, vols, symbol, dates)
        track = vcp.get("breakoutTrack")
        vcp_info = None
        if track and not track.get("broken"):
            if track.get("dayCount") == 1:
                vcp_info = {"type": "broke"}
            else:
                vcp_info = {"type": "tracking", "dayCount": track.get("dayCount")}
        elif vcp.get("status") == "final_contraction":
            vcp_info = {"type": "near"}
        elif vcp.get("status") == "contracting":
            vcp_info = {"type": "contracting"}

        chg = round(float(stock.get("change_rate") or 0), 2)
        price = float(stock.get("close") or 0)
        result = {
            "code": symbol,
            "name": stock.get("name") or symbol,
            "todayVol": today_vol,
            "volRatio": round(vol_ratio, 2),
            "chgPct": chg,
            "price": price,
            "vcpInfo": vcp_info,
        }

        if vcp_info:
            result["source"] = "VCP"
            return result

        # v2.1 coverage guard:
        # NO_VCP 必須真的有 20 個完整歷史交易日，不能把 5~19 日均線誤當 MA20。
        # 資料不足 = 不符合 NO_VCP；不改變 VCP 分支。
        if len(bars) < 20:
            return None

        # 原網站：MA20 用歷史資料，不把今天盤中價塞進 MA20。
        last20 = [b.close for b in bars[-20:]]
        ma20 = sum(last20) / len(last20) if last20 else 0
        above_ma20 = ma20 > 0 and price >= ma20
        if chg >= 3 and above_ma20:
            result["source"] = "NO_VCP"
            result["ma20"] = round(ma20, 2)
            return result
        return None


class Scanner:
    def __init__(self, adapter: FugleAdapter, bridge_url: Optional[str]):
        self.adapter = adapter
        self.selector = StrongSelector()
        self.bridge_url = bridge_url
        self.state = load_json(STATE_FILE, {"discovered": {}})
        if not isinstance(self.state.get("discovered"), dict):
            self.state = {"discovered": {}}

    def already_sent(self, d: str, symbol: str) -> bool:
        return symbol in self.state["discovered"].get(d, {})

    def mark_sent(self, d: str, symbol: str, payload: Dict[str, Any]) -> None:
        self.state["discovered"].setdefault(d, {})[symbol] = payload
        # 僅保留最近 10 個日期，避免 state 無限長。
        keys = sorted(self.state["discovered"].keys())
        for old in keys[:-10]:
            self.state["discovered"].pop(old, None)
        save_json_atomic(STATE_FILE, self.state)

    def handoff_hit(self, hit: Dict[str, Any], snap_date: str) -> bool:
        symbol = hit["code"]
        if self.already_sent(snap_date, symbol):
            return False
        payload = {
            "stock_id": symbol,
            "date": snap_date,
            "discovered_at": now_tw().strftime("%H:%M:%S"),
            "source": hit["source"],
            "name": hit["name"],
            "vol_ratio": hit["volRatio"],
            "change_pct": hit["chgPct"],
        }
        # Only a completed per-symbol audit may reach here. Dedupe is written
        # strictly after a successful bridge handoff (or explicit dry-run).
        self.bridge_send(payload)
        self.mark_sent(snap_date, symbol, payload)
        append_event({"ts": iso_now(), "type": "discovery", **payload})
        return True

    def bridge_send(self, payload: Dict[str, Any]) -> None:
        if not self.bridge_url:
            print(f"[DISCOVERY][DRY] {payload['stock_id']} {payload['date']} "
                  f"{payload['discovered_at']} source={payload['source']}")
            return

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.bridge_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = r.read().decode("utf-8", errors="replace")
                if r.status < 200 or r.status >= 300:
                    raise RuntimeError(f"Bridge HTTP {r.status}: {resp[:300]}")
                print(f"[BRIDGE] {payload['stock_id']} -> HTTP {r.status}")
        except Exception as e:
            # handoff 失敗不能先 dedupe；下輪要能重試。
            raise RuntimeError(f"Bridge handoff failed: {e}") from e

    def scan_once(self) -> List[Dict[str, Any]]:
        started = time.monotonic()
        snaps = self.adapter.snapshot()
        print(f"[A DIAG] snapshot_done rows={len(snaps)}", flush=True)
        if not snaps:
            raise AuditStop("empty Fugle Snapshot")

        dates = {str(x.get("date") or "")[:10] for x in snaps if x.get("date")}
        if len(dates) != 1:
            raise AuditStop(f"Snapshot identity date mismatch: {sorted(dates)}")
        snap_date = next(iter(dates))

        # Live production：Snapshot 必須是台北今天。
        today = now_tw().date().isoformat()
        if snap_date != today:
            raise AuditStop(f"stale Snapshot: snapshot={snap_date}, today={today}")

        # 先用不需要額外 API 的條件縮小候選；產業排除稍後做。
        candidates = [
            s for s in snaps
            if self.selector.basic_code_ok(s["stock_id"])
            and float(s.get("change_rate") or 0) > 0
        ]
        print(f"[A DIAG] first_gate_done candidates={len(candidates)}", flush=True)

        selected: List[Dict[str, Any]] = []
        for idx, s in enumerate(candidates, 1):
            symbol = s["stock_id"]

            # Same stock/day is already owned by B after a successful handoff.
            # Do not spend Fugle quota re-auditing it every scan.
            if self.already_sent(snap_date, symbol):
                continue

            print(f"[A DIAG] candidate_start {idx}/{len(candidates)} symbol={symbol}", flush=True)
            try:
                meta = self.adapter.ticker(symbol)
                if not self.selector.meta_ok(meta):
                    continue
                bars = self.adapter.daily_history(symbol, snap_date)
                f10, avg5_1m, fdays = self.adapter.estimated_vr5_parts(symbol, snap_date, now_tw())
                today_vol = float(s.get("total_volume") or 0.0)
                est_vr5 = (today_vol / f10) / avg5_1m
                s_for_select = dict(s)
                s_for_select["_estimated_vr5"] = est_vr5
                hit = self.selector.select_one(s_for_select, meta, bars)
                if hit:
                    hit["estimatedVr5"] = round(est_vr5, 4)
                    hit["f10"] = round(f10, 6)
                    hit["f10Days"] = int(fdays)
                if hit:
                    selected.append(hit)
                    # Production handoff is per-symbol and immediate: once this
                    # symbol's complete A audit passes, B starts immediately.
                    # A later API failure on another symbol cannot erase it.
                    handed = self.handoff_hit(hit, snap_date)
                    print(
                        f"[A HANDOFF] symbol={symbol} handed={handed} "
                        f"source={hit['source']}",
                        flush=True,
                    )
                print(f"[A DIAG] candidate_done {idx}/{len(candidates)} symbol={symbol} selected={bool(hit)}", flush=True)
            except AuditStop:
                raise
            except Exception as e:
                # 單股資料異常不應被解讀為不符合；記錄後跳過，不發 signal。
                append_event({
                    "ts": iso_now(), "type": "candidate_error",
                    "symbol": symbol, "error": f"{type(e).__name__}: {e}",
                })

        selected.sort(key=lambda x: x["volRatio"], reverse=True)

        elapsed = time.monotonic() - started
        print(
            f"[SCAN] {iso_now()} snapshot={len(snaps)} "
            f"first_gate={len(candidates)} selected={len(selected)} "
            f"elapsed={elapsed:.2f}s",
            flush=True,
        )
        return selected


def run_self_test() -> None:
    # 純邏輯測試，不打 Fugle、不打 Bridge、不讀寫 production track。
    print("=" * 88)
    print("A SCANNER V2.2 | SELF TEST")
    print("=" * 88)

    assert StrongSelector.basic_code_ok("3714")
    assert not StrongSelector.basic_code_ok("0050")
    assert not StrongSelector.basic_code_ok("12345")
    assert StrongSelector.meta_ok({"market": "TSE", "securityType": "01", "industry": "26"})
    assert not StrongSelector.meta_ok({"market": "TSE", "securityType": "01", "industry": "17"})
    assert not StrongSelector.meta_ok({"market": "ESB", "securityType": "01", "industry": "26"})

    # NO_VCP gate 的 deterministic fixture。
    bars = []
    d0 = date(2026, 1, 1)
    for i in range(70):
        bars.append(DailyBar((d0 + timedelta(days=i)).isoformat(), 100.0, 1000.0))

    s = StrongSelector(track_path=None)
    # self-test 完全不讀寫 production track。
    old_track = dict(s.track)
    stock = {
        "stock_id": "3714", "name": "TEST",
        "change_rate": 3.2, "total_amount": 60_000_000,
        "total_volume": 6000, "close": 103.2, "date": "2026-03-20",
        "_estimated_vr5": 1.50,
    }
    meta = {"market": "TSE", "securityType": "01", "industry": "26"}
    hit = s.select_one(stock, meta, bars, inject_snapshot_today=False)
    s.track = old_track
    assert hit is not None and hit["source"] == "NO_VCP", hit
    assert hit["volRatio"] == 1.5, hit

    stock2 = dict(stock)
    stock2["change_rate"] = 2.99
    hit2 = s.select_one(stock2, meta, bars, inject_snapshot_today=False)
    assert hit2 is None

    stock3 = dict(stock)
    stock3["total_volume"] = 3999
    assert s.select_one(stock3, meta, bars, inject_snapshot_today=False) is not None

    stock149 = dict(stock)
    stock149["_estimated_vr5"] = 1.4999
    assert s.select_one(stock149, meta, bars, inject_snapshot_today=False) is None

    stock150 = dict(stock)
    stock150["_estimated_vr5"] = 1.5000
    assert s.select_one(stock150, meta, bars, inject_snapshot_today=False) is not None

    # v2.1: NO_VCP MA20 coverage boundary.
    # 19 個完整歷史交易日不得把 MA19 當 MA20；20 日才可進 NO_VCP。
    short19 = bars[-19:]
    hit19 = s.select_one(stock, meta, short19, inject_snapshot_today=False)
    assert hit19 is None, hit19
    exact20 = bars[-20:]
    hit20 = s.select_one(stock, meta, exact20, inject_snapshot_today=False)
    assert hit20 is not None and hit20["source"] == "NO_VCP", hit20

    print("[PASS] code exclusion")
    print("[PASS] industry / ESB exclusion")
    print("[PASS] old 50m / 4000 / raw VR5 gates removed")
    print("[PASS] Fugle Estimated VR5 1.4999 BLOCK / 1.5000 PASS")
    print("[PASS] NO_VCP >=3% + MA20")
    print("[PASS] NO_VCP MA20 coverage: 19 days BLOCK / 20 days PASS")
    print("[PASS] self-test completed")
    print("NO NETWORK | NO BRIDGE | NO PRODUCTION SIGNAL")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fugle A Scanner v2")
    ap.add_argument("--once", action="store_true", help="只掃一次（本機測試）")
    ap.add_argument("--self-test", action="store_true", help="只跑 deterministic logic tests")
    ap.add_argument("--interval", type=float, default=SCAN_INTERVAL_DEFAULT,
                    help="盤中掃描週期秒數，預設 5")
    ap.add_argument("--bridge-url", default=None,
                    help="例如 http://127.0.0.1:8765/discovery；不給則 DRY RUN")
    ap.add_argument("--ignore-market-hours", action="store_true",
                    help="開發測試用；正式雲端不要使用")
    args = ap.parse_args()

    if args.self_test:
        run_self_test()
        return 0
    if args.interval < 1:
        print("AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL")
        print("interval must be >= 1 second")
        return 2

    ensure_outdir()
    try:
        key = fugle_key()
        adapter = FugleAdapter(key)
        scanner = Scanner(adapter, args.bridge_url)
    except AuditStop as e:
        print("AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL")
        print(str(e))
        return 2

    print("=" * 88)
    print("FUGLE A SCANNER V2.3 | AUTO STRONG-STOCK DISCOVERY")
    print("=" * 88)
    print(f"interval       = {args.interval:g}s")
    print(f"bridge         = {args.bridge_url or 'OFF / DRY RUN'}")
    print("market         = TSE + OTC | COMMONSTOCK")
    print("production     = A DISCOVERY ONLY | B DOES P1/A/B/C")
    print("volume gate    = Fugle Estimated VR5 >= 1.5 FIXED")
    print(f"output         = {OUTDIR}")
    print()

    if args.once:
        try:
            scanner.scan_once()
            return 0
        except AuditStop as e:
            print("AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL")
            print(str(e))
            return 2

    # 雲端常駐：不用 cron 每 5 秒叫一次；worker 自己常駐。
    while True:
        dt = now_tw()
        if args.ignore_market_hours or is_market_window(dt):
            tick = time.monotonic()
            try:
                scanner.scan_once()
            except AuditStop as e:
                print("AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL")
                print(str(e))
                append_event({"ts": iso_now(), "type": "audit_stop", "error": str(e)})
                # v2.2：audit 失敗仍 fail-closed，不發 signal；
                # 但盤中只等正常掃描週期後重新驗證，避免一次短暫 API 抖動造成 60 秒盲區。
                time.sleep(max(1.0, args.interval))
                continue
            except Exception as e:
                print(f"[ERROR] {type(e).__name__}: {e}")
                append_event({"ts": iso_now(), "type": "runtime_error", "error": str(e)})

            spent = time.monotonic() - tick
            time.sleep(max(0.1, args.interval - spent))
        else:
            # 非盤中低頻等待；電腦/雲端 service 不需要重啟。
            time.sleep(20)


if __name__ == "__main__":
    raise SystemExit(main())