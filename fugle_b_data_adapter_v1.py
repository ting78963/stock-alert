# -*- coding: utf-8 -*-
"""
fugle_b_data_adapter_v1.py

B Data Adapter v1
=================
Goal:
  Validate one-stock production data continuity:
  Fugle REST intraday 1m backfill -> WebSocket candles -> one canonical minute store.

This version deliberately DOES NOT implement:
  - Strong scanner (A)
  - Attack / A2
  - Frozen Early / D-G-F
  - A/B/C classification
  - Buy signal
  - LINE notification

Why:
  Before attaching the already-frozen trend semantics, prove that the production
  Fugle feed can be normalized and reconciled without duplicate/conflicting bars.

Read-only:
  Does not modify research/data folders.
  Optional diagnostic output is written beside this script under _production_output.

Usage:
  py -3.14 fugle_b_data_adapter_v1.py 3714
  py -3.14 fugle_b_data_adapter_v1.py 2330 --minutes 5

Expected runtime:
  REST-only/off-market: ~1-3 sec.
  During market with WebSocket watch: user-selected --minutes (default 3 min).
Main bottleneck:
  Network/WebSocket waiting for minute updates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ_TAIPEI = timezone(timedelta(hours=8))
REST_BASE = "https://api.fugle.tw/marketdata/v1.0/stock"
WS_URL = "wss://api.fugle.tw/marketdata/v1.0/stock/streaming"
STRONG_HTML = Path.home() / "Desktop" / "強勢選股" / "index.html"
HTTP_TIMEOUT = 15
EPS = 1e-9


def banner(s: str) -> None:
    print("\n" + "=" * 112)
    print(s)
    print("=" * 112)


def redact(s: Any) -> str:
    x = str(s)
    x = re.sub(r'(?i)(x-api-key|apikey|api[_-]?key|token)(\s*[:=]\s*)([^\s,;"\']+)',
               r'\1\2<REDACTED>', x)
    x = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
               '<REDACTED>', x)
    return x[:900]


def load_api_key() -> tuple[str, str]:
    env = os.environ.get("FUGLE_API_KEY", "").strip()
    if env:
        return env, "FUGLE_API_KEY environment variable"

    roots = [Path.home() / "Desktop", Path.home() / "Downloads", Path.home() / "Documents"]
    candidates: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for pat in ("Fugle*_ready.py", "fugle*_ready.py", "Fugle*.py", "fugle*.py"):
            try:
                for p in root.rglob(pat):
                    rp = str(p.resolve())
                    if rp not in seen and p.is_file() and p.resolve() != Path(__file__).resolve():
                        seen.add(rp)
                        candidates.append(p)
            except (OSError, PermissionError):
                pass

    preferred = {
        "Fugle_live_KBar_test_ready.py": 0,
        "Fugle_historical_5day_volume_test_ready.py": 1,
        "Fugle_snapshot_strong_test_ready.py": 2,
    }
    candidates.sort(key=lambda p: (preferred.get(p.name, 99), len(str(p)), str(p).lower()))

    patterns = [
        r'(?m)^\s*API_KEY\s*=\s*["\']([^"\']{16,})["\']',
        r'(?m)^\s*FUGLE_API_KEY\s*=\s*["\']([^"\']{16,})["\']',
        r'(?m)^\s*key\s*=\s*["\']([^"\']{16,})["\']',
    ]
    for p in candidates:
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except (OSError, PermissionError):
            continue
        for pat in patterns:
            m = re.search(pat, txt)
            if m:
                return m.group(1).strip(), f"existing local Fugle script: {p}"

    if STRONG_HTML.exists():
        try:
            txt = STRONG_HTML.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            txt = ""
        for pat in [
            r'FUGLE_API_KEY\s*["\']?\s*[:=]\s*["\']([^"\']{16,})["\']',
            r'["\'](?:fugleApiKey|fugle_api_key|apiKey)["\']\s*:\s*["\']([^"\']{16,})["\']',
        ]:
            m = re.search(pat, txt, flags=re.I)
            if m:
                return m.group(1).strip(), str(STRONG_HTML)

    raise RuntimeError("找不到 Fugle API key；STOP，不猜測 key。")


def parse_dt(v: Any) -> datetime:
    s = str(v or "").strip()
    if not s:
        raise ValueError("empty datetime")
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        # Fugle Taiwan stock timestamps are interpreted as Taiwan local if no offset.
        dt = dt.replace(tzinfo=TZ_TAIPEI)
    else:
        dt = dt.astimezone(TZ_TAIPEI)
    return dt


def minute_key(v: Any) -> str:
    return parse_dt(v).strftime("%Y-%m-%d %H:%M")


def num(v: Any, field: str) -> float:
    if v is None:
        raise ValueError(f"{field}=None")
    return float(v)


@dataclass(frozen=True)
class Bar:
    minute: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str

    @staticmethod
    def from_obj(obj: dict[str, Any], source: str) -> "Bar":
        # REST commonly uses date; streaming payload can vary by envelope/version.
        dtv = obj.get("date") or obj.get("time") or obj.get("timestamp")
        return Bar(
            minute=minute_key(dtv),
            open=num(obj.get("open"), "open"),
            high=num(obj.get("high"), "high"),
            low=num(obj.get("low"), "low"),
            close=num(obj.get("close"), "close"),
            volume=num(obj.get("volume"), "volume"),
            source=source,
        )

    def values(self) -> tuple[float, float, float, float, float]:
        return self.open, self.high, self.low, self.close, self.volume


def same_bar(a: Bar, b: Bar) -> bool:
    return all(abs(x-y) <= EPS for x, y in zip(a.values(), b.values()))


def rest_get(api_key: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = REST_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"X-API-KEY": api_key, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        if not (200 <= resp.status < 300):
            raise RuntimeError(f"HTTP {resp.status}: {raw[:500]}")
        return json.loads(raw)


def fetch_rest_bars(api_key: str, symbol: str) -> tuple[dict[str, Any], list[Bar]]:
    payload = rest_get(api_key, f"/intraday/candles/{symbol}",
                       {"timeframe": "1", "sort": "asc"})
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        raise RuntimeError("REST payload.data is not a list")
    bars: list[Bar] = []
    for i, x in enumerate(rows):
        if not isinstance(x, dict):
            raise RuntimeError(f"REST row {i} is not an object")
        bars.append(Bar.from_obj(x, "REST"))
    return payload, bars


def audit_rest(payload: dict[str, Any], symbol: str, bars: list[Bar]) -> None:
    banner("AUDIT 1 | DATA SOURCE / SAMPLE IDENTITY / COVERAGE")
    got_symbol = str(payload.get("symbol", ""))
    timeframe = str(payload.get("timeframe", ""))
    print(f"Requested symbol : {symbol}")
    print(f"Returned symbol  : {got_symbol}")
    print(f"Timeframe        : {timeframe}")
    print(f"REST rows        : {len(bars)}")

    if got_symbol and got_symbol != symbol:
        raise RuntimeError(f"sample identity mismatch: requested={symbol}, returned={got_symbol}")
    if timeframe and timeframe != "1":
        raise RuntimeError(f"timeframe mismatch: expected 1, got {timeframe}")
    if not bars:
        raise RuntimeError("no REST 1-minute bars returned")

    minutes = [b.minute for b in bars]
    dup = len(minutes) - len(set(minutes))
    backwards = sum(1 for a, b in zip(minutes, minutes[1:]) if b <= a)
    bad_ohlc = sum(
        1 for b in bars
        if b.high + EPS < max(b.open, b.close, b.low)
        or b.low - EPS > min(b.open, b.close, b.high)
        or b.volume < 0
    )

    print(f"First minute     : {minutes[0]}")
    print(f"Last minute      : {minutes[-1]}")
    print(f"Duplicate minute : {dup}")
    print(f"Non-increasing   : {backwards}")
    print(f"Bad OHLC/volume  : {bad_ohlc}")

    if dup or backwards or bad_ohlc:
        raise RuntimeError(
            f"REST integrity failed: duplicate={dup}, non_increasing={backwards}, bad_ohlc={bad_ohlc}"
        )
    print("PASS")


def is_regular_session_now() -> bool:
    n = datetime.now(TZ_TAIPEI)
    if n.weekday() >= 5:
        return False
    return dtime(8, 55) <= n.time() <= dtime(13, 40)


def extract_candle_obj(msg: dict[str, Any]) -> dict[str, Any] | None:
    """
    Be conservative: accept only an object that visibly contains OHLCV + a time field.
    We do not guess missing fields or synthesize a bar.
    """
    candidates: list[Any] = [msg.get("data")]
    data = msg.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("candle"), data.get("data")])
    candidates.append(msg)

    for x in candidates:
        if not isinstance(x, dict):
            continue
        has_time = any(k in x for k in ("date", "time", "timestamp"))
        has_ohlcv = all(k in x for k in ("open", "high", "low", "close", "volume"))
        if has_time and has_ohlcv:
            return x
    return None


def ws_watch(api_key: str, symbol: str, store: dict[str, Bar], watch_minutes: float) -> dict[str, Any]:
    try:
        import websocket  # type: ignore
    except Exception:
        raise RuntimeError("缺少 websocket-client；請先執行 py -3.14 -m pip install websocket-client")

    stats = {
        "messages": 0,
        "candle_messages": 0,
        "new_minutes": 0,
        "exact_duplicates": 0,
        "conflicts": 0,
        "errors": [],
    }

    ws = None
    try:
        ws = websocket.create_connection(
            WS_URL, timeout=8, sslopt={"cert_reqs": ssl.CERT_REQUIRED}
        )
        ws.send(json.dumps({"event": "auth", "data": {"apikey": api_key}}))

        deadline = time.time() + 8
        authed = False
        while time.time() < deadline:
            msg = json.loads(ws.recv())
            stats["messages"] += 1
            if msg.get("event") == "authenticated":
                authed = True
                break
            if msg.get("event") == "error":
                raise RuntimeError("WebSocket auth error: " + redact(json.dumps(msg, ensure_ascii=False)))
        if not authed:
            raise RuntimeError("WebSocket authentication confirmation timeout")

        ws.send(json.dumps({
            "event": "subscribe",
            "data": {"channel": "candles", "symbol": symbol},
        }))

        deadline = time.time() + 8
        subscribed = False
        while time.time() < deadline:
            msg = json.loads(ws.recv())
            stats["messages"] += 1
            if msg.get("event") == "subscribed":
                subscribed = True
                break
            if msg.get("event") == "error":
                raise RuntimeError("WebSocket subscribe error: " + redact(json.dumps(msg, ensure_ascii=False)))
        if not subscribed:
            raise RuntimeError("WebSocket subscription acknowledgement timeout")

        print(f"WebSocket authenticated + subscribed: candles / {symbol}")
        print(f"Watching for {watch_minutes:g} minute(s)... Ctrl+C 可提早結束。")

        ws.settimeout(2)
        end_at = time.time() + watch_minutes * 60.0
        while time.time() < end_at:
            try:
                raw = ws.recv()
            except Exception as e:
                # websocket timeout is normal while waiting.
                if e.__class__.__name__ in ("WebSocketTimeoutException", "TimeoutError"):
                    continue
                raise

            stats["messages"] += 1
            try:
                msg = json.loads(raw)
            except Exception:
                stats["errors"].append("non-json websocket message")
                continue

            if msg.get("event") == "error":
                stats["errors"].append(redact(json.dumps(msg, ensure_ascii=False)))
                continue

            obj = extract_candle_obj(msg)
            if obj is None:
                continue

            try:
                bar = Bar.from_obj(obj, "WS")
            except Exception as e:
                stats["errors"].append("candle parse: " + redact(repr(e)))
                continue

            stats["candle_messages"] += 1
            old = store.get(bar.minute)
            if old is None:
                store[bar.minute] = bar
                stats["new_minutes"] += 1
                print(
                    f"[NEW] {bar.minute} "
                    f"O={bar.open:g} H={bar.high:g} L={bar.low:g} C={bar.close:g} V={bar.volume:g}"
                )
            elif same_bar(old, bar):
                stats["exact_duplicates"] += 1
            else:
                # Do NOT silently overwrite. A live/in-progress minute may evolve;
                # record it as a reconciliation event for this audit version.
                stats["conflicts"] += 1
                print(
                    f"[RECONCILE] {bar.minute} REST/old={old.values()} WS/new={bar.values()}"
                )
                store[bar.minute] = bar

        return stats
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def final_audit(initial_minutes: set[str], store: dict[str, Bar], stats: dict[str, Any] | None) -> None:
    banner("AUDIT 2 | REST -> WEBSOCKET RECONCILIATION")
    keys = sorted(store)
    dup = len(keys) - len(set(keys))
    backwards = sum(1 for a, b in zip(keys, keys[1:]) if b <= a)

    print(f"Initial REST unique minutes : {len(initial_minutes)}")
    print(f"Canonical store minutes     : {len(keys)}")
    if keys:
        print(f"Canonical first             : {keys[0]}")
        print(f"Canonical last              : {keys[-1]}")
    print(f"Duplicate canonical keys    : {dup}")
    print(f"Non-increasing keys         : {backwards}")

    if stats is not None:
        print(f"WS messages                 : {stats['messages']}")
        print(f"WS candle messages          : {stats['candle_messages']}")
        print(f"WS new minutes              : {stats['new_minutes']}")
        print(f"WS exact duplicates         : {stats['exact_duplicates']}")
        print(f"WS reconcile events         : {stats['conflicts']}")
        print(f"WS parse/server errors      : {len(stats['errors'])}")
        for e in stats["errors"][:5]:
            print("  -", e)

    if dup or backwards:
        raise RuntimeError("canonical minute-store integrity failed")

    # Important: do not call absence of a calendar minute a failure because Taiwan
    # stocks may have no trade in that minute. We audit source continuity by key/order,
    # and later compare replay semantics against frozen benchmark cases.
    print("PASS: canonical minute keys are unique and ordered.")
    print("NOTE: no-trade clock minutes are NOT synthesized or forward-filled.")


def write_diagnostic(symbol: str, store: dict[str, Bar]) -> Path:
    outdir = Path(__file__).resolve().parent / "_production_output" / "b_data_adapter_v1"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{datetime.now(TZ_TAIPEI).date().isoformat()}_{symbol}_canonical_minutes.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for k in sorted(store):
            b = store[k]
            f.write(json.dumps({
                "minute": b.minute,
                "open": b.open, "high": b.high, "low": b.low,
                "close": b.close, "volume": b.volume,
                "last_source": b.source,
            }, ensure_ascii=False) + "\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="2330", help="股票代號，例如 3714")
    ap.add_argument("--minutes", type=float, default=3.0,
                    help="WebSocket 監看分鐘數；盤中預設 3")
    ap.add_argument("--force-ws", action="store_true",
                    help="非盤中也嘗試連 WebSocket（可能沒有 candle event）")
    ap.add_argument("--no-output", action="store_true",
                    help="不寫 diagnostic JSONL")
    args = ap.parse_args()

    symbol = re.sub(r"\D", "", args.symbol)
    if not symbol:
        print("ERROR: 無效股票代號")
        return 2

    banner("FUGLE B DATA ADAPTER | REST BACKFILL -> WEBSOCKET | v1")
    print(f"Symbol           : {symbol}")
    print("Trend logic      : DISABLED")
    print("A/B/C            : DISABLED")
    print("LINE notification: DISABLED")
    print("No future data / No synthesized minute / No forward fill")

    try:
        api_key, source = load_api_key()
        print(f"API key source   : {source}")
        print("API key value    : <REDACTED>")

        t0 = time.perf_counter()
        payload, bars = fetch_rest_bars(api_key, symbol)
        print(f"REST latency     : {time.perf_counter()-t0:.3f}s")

        audit_rest(payload, symbol, bars)

        store: dict[str, Bar] = {b.minute: b for b in bars}
        initial = set(store)

        stats = None
        if args.force_ws or is_regular_session_now():
            banner("LIVE WEBSOCKET")
            try:
                stats = ws_watch(api_key, symbol, store, max(0.1, args.minutes))
            except KeyboardInterrupt:
                print("\nUser stopped WebSocket watch.")
            final_audit(initial, store, stats)
        else:
            banner("LIVE WEBSOCKET")
            print("SKIP: 現在不在台股一般盤中時段。")
            print("REST backfill audit仍有效；盤中再跑一次即可驗證 REST -> WS 接續。")
            print("若只是要測連線，可加 --force-ws。")
            final_audit(initial, store, None)

        if not args.no_output:
            out = write_diagnostic(symbol, store)
            print(f"\nDiagnostic output: {out}")

        banner("RESULT")
        print("B DATA ADAPTER v1: DATA-LAYER AUDIT PASS")
        print("This does NOT yet authorize Attack/A2/Frozen-Early interpretation.")
        print("Next required audit: compare Fugle production bars/replay against frozen benchmark semantics.")
        return 0

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        print(f"\nHTTP ERROR {e.code}: {redact(body or e)}")
    except Exception as e:
        print("\nERROR:", redact(repr(e)))

    print("\nAUDIT FAILED -> STOP -> NO RESEARCH INTERPRETATION")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())