#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fugle_a_scanner_v2_4.py

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
import hashlib
import json
import math
import os
import queue
import re
import sqlite3
import sys
import threading
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
LEGACY_OUTDIR = Path(__file__).resolve().parent / "_production_output" / "fugle_a_scanner_v2"


def resolve_a_state_dir(legacy_outdir: Path, environ: Optional[Dict[str, str]] = None) -> Path:
    """Use an explicit A_STATE_DIR, else the existing Worker state root, else legacy path."""
    env = os.environ if environ is None else environ
    explicit = str(env.get("A_STATE_DIR", "")).strip()
    if explicit:
        return Path(explicit).expanduser()
    production_root = str(env.get("PRODUCTION_STATE_DIR", "")).strip()
    if production_root:
        return Path(production_root).expanduser() / "a_scanner_v2"
    return Path(legacy_outdir)


OUTDIR = resolve_a_state_dir(LEGACY_OUTDIR)
STATE_FILE = OUTDIR / "state.json"
TRACK_FILE = OUTDIR / "vcp_breakout_track_v2.json"
CACHE_FILE = OUTDIR / "cache.json"
HISTORY_CACHE_FILE = OUTDIR / "a_history_cache_v2_4.json"
F11_METADATA_CACHE_FILE = Path("/var/data/stock-alert/a_f11_metadata_v1.json") if Path("/var/data").exists() else (OUTDIR / "a_f11_metadata_v1.json")
# Explicit staging opt-in; production defaults stay unchanged.
F11_OFFLINE_STAGING_FILE = Path("/var/data/stock-alert/f11-staging/a_f11_staging_v1.json")
F11_OFFLINE_STAGING_ENABLED = os.environ.get("A_F11_OFFLINE_STAGING", "") == "1"
SHADOW_AUDIT_ROOT = Path("/var/data/stock-alert/a_queue_shadow_audit") if Path("/var/data").exists() else (LEGACY_OUTDIR / "a_queue_shadow_audit")
A_SCAN_MOTHER_ROOT = Path("/var/data/stock-alert/a_scan_mother") if Path("/var/data").exists() else (LEGACY_OUTDIR / "a_scan_mother")

# 對應原網站 excludedKeywords：
# 食品工業、造紙工業、建材營造、航運、觀光餐旅、金融保險、
# 貿易百貨、文化創意、生技醫療
EXCLUDED_INDUSTRY_CODES = {"02", "09", "14", "15", "16", "17", "18", "22", "32"}

ESTIMATED_VR5_MIN = 1.5
EVG_MIN_PCT = 50.0
HISTORY_429_BACKOFF_SEC = 60.0
HISTORY_BACKUP_FAILURE_COOLDOWN_SEC = 15.0
HISTORY_BACKUP_MAX_429_RETRIES = 2  # at most 3 HTTP attempts per queued job
RAW_VR5_MIN = 1.5          # SPECIAL priority only; never a handoff gate
EARLY_VOLUME_MIN = 4_000   # 09:01-09:09
REGULAR_VOLUME_MIN = 2_000 # 09:10+
SCAN_INTERVAL_DEFAULT = 5.0
OPEN_HM = (9, 0)
CLOSE_HM = (13, 30)
# Isolated candidate; never enabled in the formal entry point.
LAYERED_A_ENABLED = os.environ.get("A_LAYERED_A_ENABLED", "") == "1"
SURGE_VARIANT = "OLD_A_SNAPSHOT_DERIVED_SURGE_V1"


class AuditStop(RuntimeError):
    pass


def now_tw() -> datetime:
    return datetime.now(TZ)


def iso_now() -> str:
    return now_tw().isoformat(timespec="seconds")


def ensure_outdir() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)


_MIGRATABLE_STATE_NAMES = (
    "state.json",
    "vcp_breakout_track_v2.json",
    "cache.json",
    "a_history_cache_v2_4.json",
    "a_f11_metadata_v1.json",
    "events.jsonl",
)
_AUTHORITATIVE_JSON_NAMES = frozenset(_MIGRATABLE_STATE_NAMES[:-1])
_STATE_MIGRATION_MARKER = ".a_state_migration_v1.json"
_STATE_MIGRATION_LOCK = ".a_state_migration_v1.lock"


def _read_migration_value(path: Path) -> Any:
    try:
        if path.name == "events.jsonl":
            return path.read_bytes()
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value
    except Exception as exc:
        raise AuditStop(f"A_STATE_MIGRATION_INVALID:{path.name}:{type(exc).__name__}") from exc


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".migrate.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with tmp.open("xb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        # Deliberately leave any interrupted temporary artifact for inspection.
        raise


def initialize_state_paths(legacy_dir: Optional[Path] = None, target_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Initialize the A state root without overwriting or deleting legacy state.

    First use copies only missing files, validates object-shaped JSON, and writes
    a marker after all copies are durable. Conflicting or damaged state fails
    closed. The legacy source is retained unchanged for rollback/reconciliation.
    """
    legacy = Path(legacy_dir or LEGACY_OUTDIR)
    target = Path(target_dir or OUTDIR)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise AuditStop(f"A_STATE_TARGET_UNAVAILABLE:{type(exc).__name__}") from exc
    if legacy.resolve() == target.resolve():
        return {"mode": "legacy_in_place", "copied": [], "target": str(target)}

    marker = target / _STATE_MIGRATION_MARKER
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            if data.get("version") != 1 or data.get("target_root") != str(target.resolve()):
                raise ValueError("marker identity mismatch")
        except Exception as exc:
            raise AuditStop(f"A_STATE_MIGRATION_MARKER_INVALID:{type(exc).__name__}") from exc
        if not (target / "state.json").is_file():
            raise AuditStop("A_STATE_MISSING_AFTER_MIGRATION:manual_reconciliation_required")
        # Do not recopy stale legacy files after the new root starts receiving updates.
        for name in _MIGRATABLE_STATE_NAMES[:-1]:
            p = target / name
            if p.exists():
                _read_migration_value(p)
        return {"mode": "marker_verified", "copied": [], "target": str(target)}

    if not (legacy / "state.json").is_file() and not (target / "state.json").is_file() and legacy.resolve() != target.resolve():
        raise AuditStop("A_STATE_MISSING_INITIALIZATION_REQUIRED:preserve_or_reconcile_same_day_state")

    lock = target / _STATE_MIGRATION_LOCK
    try:
        with lock.open("x", encoding="utf-8") as f:
            f.write(f"pid={os.getpid()}\n")
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError as exc:
        raise AuditStop("A_STATE_MIGRATION_LOCK_PRESENT:manual_review_required") from exc
    copied: List[str] = []
    hashes: Dict[str, str] = {}
    try:
        for name in _MIGRATABLE_STATE_NAMES:
            src, dst = legacy / name, target / name
            if not src.exists() and not dst.exists():
                continue
            source_value = _read_migration_value(src) if src.exists() else None
            target_value = _read_migration_value(dst) if dst.exists() else None
            if src.exists() and dst.exists():
                if source_value != target_value:
                    raise AuditStop(f"A_STATE_MIGRATION_CONFLICT:{name}")
                payload = src.read_bytes()
            elif src.exists():
                payload = src.read_bytes()
                _atomic_write_bytes(dst, payload)
                copied.append(name)
            else:
                payload = dst.read_bytes()
            hashes[name] = hashlib.sha256(payload).hexdigest()

        marker_data = {
            "version": 1,
            "legacy_root": str(legacy.resolve()),
            "target_root": str(target.resolve()),
            "copied_files": copied,
            "initial_file_sha256": hashes,
            "note": "migration marker only; legacy files retained; no Render state was accessed by this code",
        }
        marker_payload = (json.dumps(marker_data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        _atomic_write_bytes(marker, marker_payload)
        return {"mode": "migrated_or_initialized", "copied": copied, "target": str(target)}
    except AuditStop:
        raise
    except Exception as exc:
        raise AuditStop(f"A_STATE_MIGRATION_WRITE_FAILED:{type(exc).__name__}") from exc
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # A surviving lock safely blocks automatic initialization next time.
            pass


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if path.name in _AUTHORITATIVE_JSON_NAMES and not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value
    except Exception as exc:
        if path.name in _AUTHORITATIVE_JSON_NAMES:
            raise AuditStop(f"A_STATE_READ_FAILED:{path.name}:{type(exc).__name__}") from exc
        return default


def save_json_atomic(path: Path, obj: Any) -> None:
    ensure_outdir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    with tmp.open("wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_event(obj: Dict[str, Any]) -> None:
    ensure_outdir()
    p = OUTDIR / "events.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def append_queue_shadow(d: str, obj: Dict[str, Any]) -> None:
    """Shadow audit disabled. Production logic unchanged."""
    return


def record_a_scan_mother_identity(d: str, symbol: str) -> None:
    """Persist identity only for the daily A scanned candidate mother."""
    daydir = A_SCAN_MOTHER_ROOT / d
    daydir.mkdir(parents=True, exist_ok=True)
    p = daydir / "stock_ids.json"

    cache = getattr(record_a_scan_mother_identity, "_cache", None)
    if cache is None:
        cache = {}
        setattr(record_a_scan_mother_identity, "_cache", cache)

    seen = cache.get(d)
    if seen is None:
        existing = load_json(p, {"date": d, "stock_ids": []})
        ids = existing.get("stock_ids", []) if isinstance(existing, dict) else []
        seen = {str(x) for x in ids if str(x)}
        cache[d] = seen

    if symbol in seen:
        return

    seen.add(symbol)
    save_json_atomic(p, {
        "date": d,
        "stock_ids": sorted(seen),
        "count": len(seen),
        "definition": "existing A candidate after meta_ok; identity only; recorded before history readiness, VR, queue, ARM, structural and B",
    })


def http_json(url: str, api_key: Optional[str] = None, timeout: int = 15) -> Dict[str, Any]:
    headers = {"User-Agent": "fugle-a-scanner-v2.4/1.0"}
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
        self.f11_metadata_store: Dict[str, Any] = load_json(F11_METADATA_CACHE_FILE, {})
        if not isinstance(self.f11_metadata_store, dict):
            self.f11_metadata_store = {}
        symbols = self.f11_metadata_store.get("symbols")
        # Backward compatible with v2.1: reuse the symbol map across trading days.
        self.f11_metadata_cache: Dict[str, Any] = symbols if isinstance(symbols, dict) else {}
        if F11_OFFLINE_STAGING_ENABLED:
            # Fail closed before scanning; never silently fall back to synchronous HTTP.
            staging = load_json(F11_OFFLINE_STAGING_FILE, None)
            records = staging.get("symbols") if isinstance(staging, dict) else None
            if not isinstance(records, dict) or not records:
                raise AuditStop("F11 offline staging unavailable or invalid")
            self.f11_metadata_cache = records
            print(f"[A F11 OFFLINE] loaded={len(records)} path={F11_OFFLINE_STAGING_FILE}", flush=True)
        self.daily_cache: Dict[str, Tuple[str, List[DailyBar]]] = {}
        # Historical D/1m baselines are immutable for a target trading day.
        # Persist them on Render disk so a restart/scan does not refetch 10x 1m
        # sessions per candidate and trip Fugle's HTTP rate limit.
        self.history_cache: Dict[str, Any] = load_json(HISTORY_CACHE_FILE, {})
        if not isinstance(self.history_cache, dict):
            self.history_cache = {}
        self.history_backoff_until = 0.0

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

    def historical_json(self, url: str) -> Dict[str, Any]:
        # A 429 on historical endpoints must not abort the whole scan or be retried
        # every 5 seconds. Cached symbols continue; uncached symbols wait.
        if time.monotonic() < self.history_backoff_until:
            raise RuntimeError("HISTORY_BACKOFF")
        try:
            return http_json(url, self.key)
        except AuditStop as e:
            if "Fugle HTTP 429" in str(e):
                self.history_backoff_until = time.monotonic() + HISTORY_429_BACKOFF_SEC
                print(f"[A HISTORY BACKOFF] Fugle 429 -> pause uncached historical requests {HISTORY_429_BACKOFF_SEC:.0f}s; cached candidates continue", flush=True)
                raise RuntimeError("HISTORY_BACKOFF") from e
            raise

    def ticker(self, symbol: str) -> Dict[str, Any]:
        if symbol in self.meta_cache:
            return self.meta_cache[symbol]

        persisted = self.f11_metadata_cache.get(symbol)
        if isinstance(persisted, dict) and str(persisted.get("symbol") or "") == symbol:
            self.meta_cache[symbol] = persisted
            return persisted

        if F11_OFFLINE_STAGING_ENABLED:
            # Caller must defer this symbol; no network and no production cache write.
            raise RuntimeError(f"F11_OFFLINE_MISS:{symbol}")

        d = http_json(f"{BASE}/intraday/ticker/{urllib.parse.quote(symbol)}", self.key)
        if str(d.get("symbol") or "") != symbol:
            raise AuditStop(f"ticker identity mismatch: requested={symbol}, got={d.get('symbol')}")

        self.meta_cache[symbol] = d
        self.f11_metadata_cache[symbol] = d
        self.f11_metadata_store = {"symbols": self.f11_metadata_cache}
        F11_METADATA_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = F11_METADATA_CACHE_FILE.with_suffix(F11_METADATA_CACHE_FILE.suffix + ".tmp")
        tmp.write_text(json.dumps(self.f11_metadata_store, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(F11_METADATA_CACHE_FILE)
        return d

    def _shared_daily_history(self, symbol: str, snapshot_date: str) -> Optional[List[DailyBar]]:
        """Shared daily SQLite fast path; None means use existing WAIT_DATA fallback.

        Fail closed unless the last completed market session was verified externally.
        A_LAST_COMPLETED_SESSION is supplied by the premarket market-calendar updater,
        NOT inferred from an individual stock's most recent bar.
        """
        db_path = Path(os.environ.get(
            "A_SHARED_DAILY_DB", "/var/data/stock-alert/shared_history_stage_v1.sqlite3"
        ))
        required = os.environ.get("A_LAST_COMPLETED_SESSION", "").strip()
        to_d = date.fromisoformat(snapshot_date) - timedelta(days=1)
        from_d = to_d - timedelta(days=170)
        if not required or not db_path.is_file():
            return None
        try:
            verified = date.fromisoformat(required)
            if verified > to_d:
                return None
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
            try:
                status = conn.execute(
                    "SELECT covered_through FROM fetch_status WHERE symbol=?", (symbol,)
                ).fetchone()
                if not status or not status[0] or str(status[0])[:10] < required:
                    return None
                rows = conn.execute(
                    """SELECT day,close,volume_zhang FROM daily_ohlcv
                       WHERE symbol=? AND day>=? AND day<=? ORDER BY day""",
                    (symbol, from_d.isoformat(), to_d.isoformat())
                ).fetchall()
            finally:
                conn.close()
            if not rows:
                return None
            bars = []
            for ds, close, volume in rows:
                if (not isinstance(ds, str) or ds < from_d.isoformat()
                        or ds >= snapshot_date or close is None or volume is None
                        or float(close) <= 0 or float(volume) < 0):
                    return None
                bars.append(DailyBar(ds, float(close), float(volume)))
            return bars
        except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
            print(f"[A SHARED DAILY FALLBACK] symbol={symbol} reason={type(exc).__name__}")
            return None

    def daily_history_local_ready(self, symbol: str, snapshot_date: str) -> Optional[List[DailyBar]]:
        cache_key = f"{symbol}|{snapshot_date}"
        if symbol in self.daily_cache and self.daily_cache[symbol][0] == cache_key:
            return self.daily_cache[symbol][1]
        shared_bars = self._shared_daily_history(symbol, snapshot_date)
        if shared_bars is not None:
            self.daily_cache[symbol] = (cache_key, shared_bars)
            return shared_bars
        if symbol in self.daily_cache and self.daily_cache[symbol][0] == cache_key:
            return self.daily_cache[symbol][1]

        to_d = date.fromisoformat(snapshot_date) - timedelta(days=1)
        from_d = to_d - timedelta(days=170)
        store_key = "daily_static|" + symbol
        covered_key = "daily_static_covered|" + symbol

        persisted = self.history_cache.get(store_key)
        covered_through = str(self.history_cache.get(covered_key) or "")[:10]

        if not isinstance(persisted, list) or not persisted:
            prefix = "daily|" + symbol + "|"
            legacy_candidates = []
            for k, v in self.history_cache.items():
                if not isinstance(k, str) or not k.startswith(prefix) or not isinstance(v, list) or not v:
                    continue
                legacy_snapshot = k[len(prefix):]
                if legacy_snapshot and legacy_snapshot <= snapshot_date:
                    legacy_candidates.append((legacy_snapshot, v))
            if legacy_candidates:
                legacy_candidates.sort(key=lambda x: x[0])
                legacy_snapshot, persisted = legacy_candidates[-1]
                covered_through = (date.fromisoformat(legacy_snapshot) - timedelta(days=1)).isoformat()

        merged: Dict[str, DailyBar] = {}
        if isinstance(persisted, list):
            for x in persisted:
                try:
                    ds = str(x["date"])[:10]
                    close = float(x["close"])
                    vol_zhang = float(x["volume_zhang"])
                except Exception:
                    continue
                if ds and ds < snapshot_date and close > 0:
                    merged[ds] = DailyBar(ds, close, vol_zhang)

        if covered_through:
            try:
                fetch_from = date.fromisoformat(covered_through) + timedelta(days=1)
            except Exception:
                fetch_from = from_d
        elif merged:
            fetch_from = max(date.fromisoformat(ds) for ds in merged) + timedelta(days=1)
        else:
            fetch_from = from_d

        if fetch_from <= to_d:
            return None

        all_bars = sorted(merged.values(), key=lambda x: x.date)
        if any(b.date >= snapshot_date for b in all_bars):
            raise AuditStop(f"{symbol} causal history audit failed")

        bars = [b for b in all_bars if b.date >= from_d.isoformat() and b.date < snapshot_date]
        self.daily_cache[symbol] = (cache_key, bars)
        return bars

    def daily_history(self, symbol: str, snapshot_date: str) -> List[DailyBar]:
        # 必須嚴格只用 snapshot_date 之前的完整交易日。
        cache_key = f"{symbol}|{snapshot_date}"
        if symbol in self.daily_cache and self.daily_cache[symbol][0] == cache_key:
            return self.daily_cache[symbol][1]

        to_d = date.fromisoformat(snapshot_date) - timedelta(days=1)
        from_d = to_d - timedelta(days=170)
        store_key = "daily_static|" + symbol
        covered_key = "daily_static_covered|" + symbol

        persisted = self.history_cache.get(store_key)
        covered_through = str(self.history_cache.get(covered_key) or "")[:10]

        if not isinstance(persisted, list) or not persisted:
            prefix = "daily|" + symbol + "|"
            legacy_candidates = []
            for k, v in self.history_cache.items():
                if not isinstance(k, str) or not k.startswith(prefix) or not isinstance(v, list) or not v:
                    continue
                legacy_snapshot = k[len(prefix):]
                if legacy_snapshot and legacy_snapshot <= snapshot_date:
                    legacy_candidates.append((legacy_snapshot, v))
            if legacy_candidates:
                legacy_candidates.sort(key=lambda x: x[0])
                legacy_snapshot, persisted = legacy_candidates[-1]
                covered_through = (date.fromisoformat(legacy_snapshot) - timedelta(days=1)).isoformat()

        merged: Dict[str, DailyBar] = {}
        if isinstance(persisted, list):
            for x in persisted:
                try:
                    ds = str(x["date"])[:10]
                    close = float(x["close"])
                    vol_zhang = float(x["volume_zhang"])
                except Exception:
                    continue
                if ds and ds < snapshot_date and close > 0:
                    merged[ds] = DailyBar(ds, close, vol_zhang)

        if covered_through:
            try:
                fetch_from = date.fromisoformat(covered_through) + timedelta(days=1)
            except Exception:
                fetch_from = from_d
        elif merged:
            fetch_from = max(date.fromisoformat(ds) for ds in merged) + timedelta(days=1)
        else:
            fetch_from = from_d

        if fetch_from <= to_d:
            params = urllib.parse.urlencode({
                "from": fetch_from.isoformat(),
                "to": to_d.isoformat(),
                "timeframe": "D",
                "fields": "close,volume",
                "sort": "asc",
            })
            d = self.historical_json(
                f"{BASE}/historical/candles/{urllib.parse.quote(symbol)}?{params}"
            )
            if str(d.get("symbol") or "") != symbol:
                raise AuditStop(f"history identity mismatch: requested={symbol}, got={d.get('symbol')}")
            rows = d.get("data")
            if not isinstance(rows, list):
                raise AuditStop(f"{symbol} historical candles missing data[]")

            for r in rows:
                ds = str(r.get("date") or "")[:10]
                if not ds or ds >= snapshot_date:
                    continue
                try:
                    close = float(r["close"])
                    vol_zhang = float(r["volume"]) / 1000.0
                except Exception:
                    continue
                if close > 0:
                    merged[ds] = DailyBar(ds, close, vol_zhang)
            covered_through = to_d.isoformat()

        all_bars = sorted(merged.values(), key=lambda x: x.date)
        if any(b.date >= snapshot_date for b in all_bars):
            raise AuditStop(f"{symbol} causal history audit failed")

        bars = [b for b in all_bars if b.date >= from_d.isoformat() and b.date < snapshot_date]
        self.daily_cache[symbol] = (cache_key, bars)

        new_store = [{"date": b.date, "close": b.close, "volume_zhang": b.volume_zhang} for b in all_bars]
        changed = False
        if self.history_cache.get(store_key) != new_store:
            self.history_cache[store_key] = new_store
            changed = True
        if covered_through and self.history_cache.get(covered_key) != covered_through:
            self.history_cache[covered_key] = covered_through
            changed = True
        if changed:
            save_json_atomic(HISTORY_CACHE_FILE, self.history_cache)
        return bars

    def estimated_vr5_parts(self, symbol: str, snapshot_date: str, now_dt: datetime) -> Tuple[float, float, float, int]:
        """Fugle-only F10(t) + prior5 average, all from historical 1m volume."""
        cache_key = f"estvr5|{symbol}|{snapshot_date}"
        if not hasattr(self, "_estvr5_cache"):
            self._estvr5_cache = {}
        days = self._estvr5_cache.get(cache_key)
        if days is None:
            persisted = self.history_cache.get(cache_key)
            if isinstance(persisted, list) and len(persisted) >= 5:
                days = persisted
                self._estvr5_cache[cache_key] = days
        if days is None:
            # F10 FAST path: replace only historical data acquisition.
            # All EstVR5 / EVG mathematics below remain unchanged.
            f10_db = (
                Path(os.environ.get("PRODUCTION_STATE_DIR"))
                / "f10_baseline_v1.sqlite3"
                if os.environ.get("PRODUCTION_STATE_DIR")
                else (
                    Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
                    if Path("/var/data").exists()
                    else OUTDIR.parent / "f10_baseline_v1.sqlite3"
                )
            )

            if f10_db.exists():
                try:
                    conn = sqlite3.connect(
                        f"file:{f10_db}?mode=ro",
                        uri=True,
                        timeout=5,
                    )
                    try:
                        rows = conn.execute(
                            """
                            SELECT day, full, pts_json
                            FROM f10_day
                            WHERE symbol=? AND day<?
                            ORDER BY day DESC
                            LIMIT 10
                            """,
                            (symbol, snapshot_date),
                        ).fetchall()
                    finally:
                        conn.close()
                except sqlite3.Error as e:
                    raise AuditStop(
                        f"{symbol} F10 SQLite audit failed: {e}"
                    )

                # F10 incomplete / ordinary miss:
                # preserve the original Fugle OLD path below.
                if rows:
                    rows = list(reversed(rows))
                    fast_days = []
                    seen_dates = set()

                    for ds, full, pts_json in rows:
                        ds = str(ds)

                        if ds >= snapshot_date:
                            raise AuditStop(
                                f"{symbol} F10 future leakage: "
                                f"{ds}>={snapshot_date}"
                            )

                        if ds in seen_dates:
                            raise AuditStop(
                                f"{symbol} F10 duplicate session: {ds}"
                            )
                        seen_dates.add(ds)

                        try:
                            full = float(full)
                            pts_raw = json.loads(pts_json)
                        except Exception as e:
                            raise AuditStop(
                                f"{symbol} F10 malformed row {ds}: {e}"
                            )

                        if full <= 0:
                            raise AuditStop(
                                f"{symbol} F10 invalid full volume: {ds}"
                            )

                        if not isinstance(pts_raw, list) or not pts_raw:
                            raise AuditStop(
                                f"{symbol} F10 empty pts: {ds}"
                            )

                        pts = []
                        seen_minutes = set()
                        last_running = -1.0

                        for item in pts_raw:
                            if (
                                not isinstance(item, (list, tuple))
                                or len(item) != 2
                            ):
                                raise AuditStop(
                                    f"{symbol} F10 malformed point: {ds}"
                                )

                            tm = str(item[0])

                            try:
                                running = float(item[1])
                            except Exception as e:
                                raise AuditStop(
                                    f"{symbol} F10 invalid cumulative "
                                    f"{ds} {tm}: {e}"
                                )

                            if tm in seen_minutes:
                                raise AuditStop(
                                    f"{symbol} F10 duplicate minute: "
                                    f"{ds} {tm}"
                                )

                            if running < 0 or running < last_running:
                                raise AuditStop(
                                    f"{symbol} F10 invalid cumulative: "
                                    f"{ds} {tm}"
                                )

                            seen_minutes.add(tm)
                            last_running = running
                            pts.append((tm, running))

                        if abs(last_running - full) > 1e-9:
                            raise AuditStop(
                                f"{symbol} F10 full/curve mismatch: {ds}"
                            )

                        fast_days.append({
                            "date": ds,
                            "full": full,
                            "pts": pts,
                        })

                    days = fast_days
                    if len(rows) == 10:
                        self._estvr5_cache[cache_key] = days

        if days is None or len(days) < 10:
            # Staging incremental F10 fallback: reuse validated DB sessions.
            # Never refetch a day that is already in F10; fail closed on
            # excessive misses instead of generating a burst of 1m requests.
            bars = self.daily_history(symbol, snapshot_date)
            hist_dates = [b.date for b in bars[-10:]]
            if len(hist_dates) < 5:
                raise AuditStop(f"{symbol} Estimated VR5 history <5 sessions")
            existing = {str(d["date"]): d for d in (days or [])}
            missing = [ds for ds in hist_dates if ds not in existing]
            cap = int(os.environ.get("A_F10_FALLBACK_MAX_DAYS", "2"))
            if cap < 0 or cap > 2:
                raise AuditStop("A_F10_FALLBACK_MAX_DAYS must be 0..2")
            if len(missing) > cap:
                raise AuditStop(
                    f"{symbol} F10 DB incomplete: {len(missing)} missing sessions "
                    f"(cap={cap}); defer instead of bulk historical API"
                )
            # Prevent the same failed/missing session from triggering a Fugle
            # request on every 5-second scan. RAM-only, staging opt-in.
            if not hasattr(self, "_f10_fallback_attempts"):
                self._f10_fallback_attempts = {}
            cooldown = int(os.environ.get("A_F10_FALLBACK_COOLDOWN_SECONDS", "1800"))
            if cooldown < 60:
                raise AuditStop("A_F10_FALLBACK_COOLDOWN_SECONDS must be >=60")
            stamp = time.monotonic()
            for ds in missing:
                key = (symbol, ds)
                prev = self._f10_fallback_attempts.get(key)
                if prev is not None and stamp - prev < cooldown:
                    raise AuditStop(
                        f"{symbol} F10 fallback cooldown: {ds}; defer retry"
                    )
            days = [existing[ds] for ds in hist_dates if ds in existing]
            for ds in missing:
                self._f10_fallback_attempts[(symbol, ds)] = time.monotonic()
                q = urllib.parse.urlencode({
                    "timeframe": "1", "from": ds, "to": ds,
                    "fields": "open,high,low,close,volume,average", "sort": "asc",
                })
                o = self.historical_json(f"{BASE}/historical/candles/{urllib.parse.quote(symbol)}?{q}")
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
            days = sorted(days, key=lambda d: d["date"])
            if len(days) < 5:
                raise AuditStop(f"{symbol} Estimated VR5 valid sessions <5")
            self._estvr5_cache[cache_key] = days
            self.history_cache[cache_key] = days
            save_json_atomic(HISTORY_CACHE_FILE, self.history_cache)

        cutoff = now_dt.strftime("%H:%M:00")

        # Historical 1m days are fixed for this snapshot_date. Build each cutoff
        # result once, then reuse it on every 5-second A scan.
        if not hasattr(self, "_estvr5_curve_cache"):
            self._estvr5_curve_cache = {}
        curve_state = self._estvr5_curve_cache.get(cache_key)

        if curve_state is None:
            fulls = [float(d["full"]) for d in days]
            if len(fulls) < 5:
                raise AuditStop(f"{symbol} Estimated VR5 F10 valid days <5")

            avg5 = sum(fulls[-5:]) / len(fulls[-5:])
            prev1 = fulls[-1]
            if avg5 <= 0:
                raise AuditStop(f"{symbol} invalid Estimated VR5 F10/avg5")
            if prev1 <= 0:
                raise AuditStop(f"{symbol} invalid EVG previous-session volume")

            # Preserve OLD semantics exactly: each answer is the last running
            # cumulative volume whose historical timestamp is <= cutoff.
            cutoffs = sorted({
                str(tm)
                for d in days
                for tm, _running in d["pts"]
            })
            curve = {}
            positions = [0] * len(days)
            cumulatives = [0.0] * len(days)

            for curve_cutoff in cutoffs:
                fractions = []
                for i, d in enumerate(days):
                    pts = d["pts"]
                    pos = positions[i]
                    cum = cumulatives[i]
                    while pos < len(pts) and str(pts[pos][0]) <= curve_cutoff:
                        cum = float(pts[pos][1])
                        pos += 1
                    positions[i] = pos
                    cumulatives[i] = cum
                    fractions.append(cum / fulls[i])
                curve[curve_cutoff] = sum(fractions) / len(fractions)

            curve_state = {
                "curve": curve,
                "cutoffs": cutoffs,
                "avg5": avg5,
                "prev1": prev1,
                "n": len(fulls),
            }
            self._estvr5_curve_cache[cache_key] = curve_state

        cutoffs = curve_state["cutoffs"]
        curve = curve_state["curve"]

        # Match OLD <= cutoff behavior even when historical timestamps are not
        # exactly standard minute labels.
        lo, hi = 0, len(cutoffs)
        while lo < hi:
            mid = (lo + hi) // 2
            if cutoffs[mid] <= cutoff:
                lo = mid + 1
            else:
                hi = mid
        f10 = 0.0 if lo == 0 else float(curve[cutoffs[lo - 1]])
        avg5 = float(curve_state["avg5"])
        prev1 = float(curve_state["prev1"])
        n = int(curve_state["n"])

        if not math.isfinite(f10) or f10 <= 0 or avg5 <= 0:
            raise AuditStop(f"{symbol} invalid Estimated VR5 F10/avg5")
        if prev1 <= 0:
            raise AuditStop(f"{symbol} invalid EVG previous-session volume")
        return f10, avg5, prev1, n


    def prepare_f10_cache_only(self, symbols: List[str], snapshot_date: str) -> None:
        """Prime the existing OLD-A estimator cache using one read-only SQLite connection.

        Missing/incomplete histories stay unavailable; this method never calls Fugle.
        The existing estimated_vr5_parts() remains the only metric calculator.
        """
        if not hasattr(self, "_estvr5_cache"):
            self._estvr5_cache = {}
        ready = {}
        unresolved = []
        for symbol in dict.fromkeys(str(x) for x in symbols):
            key = f"estvr5|{symbol}|{snapshot_date}"
            ram = self._estvr5_cache.get(key)
            persisted = self.history_cache.get(key)
            if isinstance(ram, list) and len(ram) >= 10:
                ready[symbol] = True
            elif isinstance(persisted, list) and len(persisted) >= 10:
                self._estvr5_cache[key] = persisted
                ready[symbol] = True
            else:
                ready[symbol] = False
                unresolved.append(symbol)
        self._surge_f10_ready = ready
        if not unresolved:
            return
        db_path = (
            Path(os.environ.get("PRODUCTION_STATE_DIR")) / "f10_baseline_v1.sqlite3"
            if os.environ.get("PRODUCTION_STATE_DIR")
            else (Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
                  if Path("/var/data").exists()
                  else OUTDIR.parent / "f10_baseline_v1.sqlite3")
        )
        if not db_path.is_file():
            return
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
            try:
                for symbol in unresolved:
                    rows = conn.execute(
                        "SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",
                        (symbol, snapshot_date),
                    ).fetchall()
                    if len(rows) != 10:
                        continue
                    days = [{"date": str(day), "full": float(full),
                             "pts": [(str(tm), float(vol)) for tm, vol in json.loads(points)]}
                            for day, full, points in reversed(rows)]
                    self._estvr5_cache[f"estvr5|{symbol}|{snapshot_date}"] = days
                    ready[symbol] = True
            finally:
                conn.close()
        except (OSError, sqlite3.Error, TypeError, ValueError, KeyError):
            self._surge_f10_ready = {symbol: False for symbol in ready}
            return
        self._surge_f10_ready = ready

    def has_complete_f10_cache_only(self, symbol: str, snapshot_date: str) -> bool:
        """True only when the existing estimated_vr5_parts path cannot fall back to HTTP."""
        readiness = getattr(self, "_surge_f10_ready", None)
        if isinstance(readiness, dict):
            return readiness.get(symbol, False) is True
        key = f"estvr5|{symbol}|{snapshot_date}"
        ram = getattr(self, "_estvr5_cache", {}).get(key)
        if isinstance(ram, list):
            return len(ram) >= 10
        persisted = self.history_cache.get(key)
        # estimated_vr5_parts adopts persisted lists at >=5 rows, then falls
        # through to daily_history/API when fewer than ten are present.
        if isinstance(persisted, list) and len(persisted) >= 5:
            return len(persisted) >= 10
        db_path = (
            Path(os.environ.get("PRODUCTION_STATE_DIR")) / "f10_baseline_v1.sqlite3"
            if os.environ.get("PRODUCTION_STATE_DIR")
            else (Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
                  if Path("/var/data").exists()
                  else OUTDIR.parent / "f10_baseline_v1.sqlite3")
        )
        if not db_path.is_file():
            return False
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM f10_day WHERE symbol=? AND day<?",
                    (symbol, snapshot_date),
                ).fetchone()[0]
            finally:
                conn.close()
            return int(count) >= 10
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return False


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
        # Volume eligibility is owned by Scanner's persistent daily watchlist.
        vol_ratio = float(stock.get("_volume_display_ratio") or 0.0)

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
        if chg >= 2.5 and above_ma20:
            result["source"] = "NO_VCP"
            result["ma20"] = round(ma20, 2)
            return result
        return None


@dataclass
class WaitDataJob:
    symbol: str
    snapshot_date: str


@dataclass
class WaitDataResult:
    symbol: str
    snapshot_date: str
    ok: bool
    rows: Optional[List[Dict[str, Any]]] = None
    covered_through: Optional[str] = None
    error: Optional[str] = None
    fatal: bool = False


class WaitDataWorker:
    """
    Single background historical-D fetch worker.

    Safety:
    - A main scan never waits for this worker.
    - Only one historical-D job executes at a time.
    - Background worker never writes Production cache/state.
    - Results are returned to Scanner main thread for incorporation.
    - A symbol/date can be pending only once.
    """

    def __init__(self, api_key: str, max_pending: int = 512):
        self.api_key = api_key
        self.jobs: "queue.Queue[WaitDataJob]" = queue.Queue(maxsize=max_pending)
        self.results: "queue.Queue[WaitDataResult]" = queue.Queue()
        self.pending = set()
        self.retry_after: Dict[Tuple[str, str], float] = {}
        self.pending_lock = threading.Lock()
        self.thread = threading.Thread(
            target=self._run,
            name="a-wait-data-worker",
            daemon=True,
        )
        self.thread.start()

    def submit(self, symbol: str, snapshot_date: str) -> bool:
        key = (str(symbol), str(snapshot_date))
        with self.pending_lock:
            if key in self.pending or time.monotonic() < self.retry_after.get(key, 0.0):
                return False
            try:
                self.jobs.put_nowait(WaitDataJob(*key))
            except queue.Full:
                return False
            self.pending.add(key)
        return True

    def drain_results(self) -> List[WaitDataResult]:
        out: List[WaitDataResult] = []
        while True:
            try:
                out.append(self.results.get_nowait())
            except queue.Empty:
                break
        return out

    def _finish(self, result: WaitDataResult) -> None:
        key = (result.symbol, result.snapshot_date)
        with self.pending_lock:
            self.pending.discard(key)
            if not result.ok:
                cooldown = (HISTORY_429_BACKOFF_SEC
                            if result.error and "HISTORY_RATE_LIMITED" in result.error
                            else HISTORY_BACKUP_FAILURE_COOLDOWN_SEC)
                self.retry_after[key] = time.monotonic() + cooldown
            else:
                self.retry_after.pop(key, None)
        self.results.put(result)

    def _run(self) -> None:
        # Worker owns its own historical backoff state.
        history_backoff_until = 0.0

        while True:
            job = self.jobs.get()
            try:
                symbol = job.symbol
                snapshot_date = job.snapshot_date

                now_mono = time.monotonic()
                if now_mono < history_backoff_until:
                    time.sleep(history_backoff_until - now_mono)

                to_d = date.fromisoformat(snapshot_date) - timedelta(days=1)
                from_d = to_d - timedelta(days=170)

                q = urllib.parse.urlencode({
                    "from": from_d.isoformat(),
                    "to": to_d.isoformat(),
                    "timeframe": "D",
                    "fields": "close,volume",
                    "sort": "asc",
                })
                url = f"{BASE}/historical/candles/{urllib.parse.quote(symbol)}?{q}"

                retries_429 = 0
                while True:
                    now_mono = time.monotonic()
                    if now_mono < history_backoff_until:
                        time.sleep(history_backoff_until - now_mono)

                    try:
                        payload = http_json(url, self.api_key)
                        break
                    except AuditStop as e:
                        if "Fugle HTTP 429" in str(e):
                            retries_429 += 1
                            if retries_429 > HISTORY_BACKUP_MAX_429_RETRIES:
                                # Keep the single historical worker in cooldown
                                # even after this job exhausts its retry budget.
                                history_backoff_until = (
                                    time.monotonic() + HISTORY_429_BACKOFF_SEC
                                )
                                raise RuntimeError(f"HISTORY_RATE_LIMITED: 429 retry budget exhausted for {symbol}") from e
                            history_backoff_until = (
                                time.monotonic() + HISTORY_429_BACKOFF_SEC
                            )
                            print(
                                f"[A WAIT_DATA BACKOFF] symbol={symbol} "
                                f"date={snapshot_date} "
                                f"sleep={HISTORY_429_BACKOFF_SEC:.0f}s",
                                flush=True,
                            )
                            continue
                        raise

                if str(payload.get("symbol") or "") != symbol:
                    raise AuditStop(
                        f"WAIT_DATA identity mismatch: requested={symbol}, "
                        f"got={payload.get('symbol')}"
                    )

                data = payload.get("data")
                if not isinstance(data, list):
                    raise AuditStop(f"WAIT_DATA {symbol} historical D missing data list")

                merged: Dict[str, Dict[str, Any]] = {}
                for x in data:
                    if not isinstance(x, dict):
                        continue
                    ds = str(x.get("date") or "")[:10]
                    if not ds or ds >= snapshot_date:
                        continue
                    try:
                        close = float(x["close"])
                        volume_zhang = float(x["volume"]) / 1000.0
                    except Exception as e:
                        raise AuditStop(
                            f"WAIT_DATA {symbol} invalid D row {ds}: {e}"
                        ) from e

                    if close <= 0 or volume_zhang < 0:
                        raise AuditStop(
                            f"WAIT_DATA {symbol} invalid D values {ds}"
                        )

                    merged[ds] = {
                        "date": ds,
                        "close": close,
                        "volume_zhang": volume_zhang,
                    }

                rows = [merged[k] for k in sorted(merged)]

                self._finish(WaitDataResult(
                    symbol=symbol,
                    snapshot_date=snapshot_date,
                    ok=True,
                    rows=rows,
                    covered_through=to_d.isoformat(),
                ))

            except AuditStop as e:
                self._finish(WaitDataResult(
                    symbol=job.symbol,
                    snapshot_date=job.snapshot_date,
                    ok=False,
                    error=f"{type(e).__name__}: {e}",
                    fatal=True,
                ))
            except Exception as e:
                rate_limited = "HISTORY_RATE_LIMITED" in str(e)
                self._finish(WaitDataResult(
                    symbol=job.symbol,
                    snapshot_date=job.snapshot_date,
                    ok=False,
                    error=f"{type(e).__name__}: {e}",
                    fatal=not rate_limited,
                ))
            finally:
                self.jobs.task_done()


class Scanner:
    def __init__(self, adapter: FugleAdapter, bridge_url: Optional[str]):
        self.adapter = adapter
        self.selector = StrongSelector()
        self.bridge_url = bridge_url
        self.layered_a_enabled = LAYERED_A_ENABLED
        self.state = load_json(STATE_FILE, {"discovered": {}, "volume_armed": {}, "queue_waiting": {}})
        if not isinstance(self.state, dict):
            self.state = {}
        if not isinstance(self.state.get("discovered"), dict):
            self.state["discovered"] = {}
        if not isinstance(self.state.get("volume_armed"), dict):
            self.state["volume_armed"] = {}
        if not isinstance(self.state.get("queue_waiting"), dict):
            self.state["queue_waiting"] = {}
        if not isinstance(self.state.get("layered_handoff_unknown"), dict):
            self.state["layered_handoff_unknown"] = {}
        if not isinstance(self.state.get("layered_handoff_result"), dict):
            self.state["layered_handoff_result"] = {}
        if not isinstance(self.state.get("layered_vcp_state"), dict):
            self.state["layered_vcp_state"] = {}

        # Historical-D MISS work is isolated from the A main scan.
        # Worker performs network I/O only; Scanner main thread owns cache mutation.
        self.wait_data_worker = WaitDataWorker(self.adapter.key)

    def apply_wait_data_results(self) -> int:
        applied = 0

        for result in self.wait_data_worker.drain_results():
            if not result.ok:
                if result.fatal:
                    raise AuditStop(
                        f"WAIT_DATA fatal: symbol={result.symbol} "
                        f"date={result.snapshot_date} reason={result.error}"
                    )
                print(
                    f"[A WAIT_DATA] symbol={result.symbol} "
                    f"date={result.snapshot_date} status=RETRY "
                    f"reason={result.error}",
                    flush=True,
                )
                continue

            if result.rows is None or not result.covered_through:
                raise AuditStop(
                    f"WAIT_DATA result incomplete: {result.symbol} "
                    f"{result.snapshot_date}"
                )

            store_key = "daily_static|" + result.symbol
            covered_key = "daily_static_covered|" + result.symbol

            existing = self.adapter.history_cache.get(store_key)
            merged: Dict[str, Dict[str, Any]] = {}

            if isinstance(existing, list):
                for x in existing:
                    if not isinstance(x, dict):
                        continue
                    try:
                        ds = str(x["date"])[:10]
                        close = float(x["close"])
                        volume_zhang = float(x["volume_zhang"])
                    except Exception:
                        continue
                    if ds and ds < result.snapshot_date and close > 0:
                        merged[ds] = {
                            "date": ds,
                            "close": close,
                            "volume_zhang": volume_zhang,
                        }

            for x in result.rows:
                ds = str(x["date"])[:10]
                if ds >= result.snapshot_date:
                    raise AuditStop(
                        f"WAIT_DATA future leakage: {result.symbol} {ds} "
                        f">= {result.snapshot_date}"
                    )
                merged[ds] = {
                    "date": ds,
                    "close": float(x["close"]),
                    "volume_zhang": float(x["volume_zhang"]),
                }

            self.adapter.history_cache[store_key] = [
                merged[k] for k in sorted(merged)
            ]
            self.adapter.history_cache[covered_key] = result.covered_through

            # Invalidate symbol RAM view so next scan rebuilds from merged cache.
            self.adapter.daily_cache.pop(result.symbol, None)

            applied += 1
            print(
                f"[A WAIT_DATA] symbol={result.symbol} "
                f"date={result.snapshot_date} status=READY "
                f"rows={len(result.rows)}",
                flush=True,
            )

        return applied

    def already_sent(self, d: str, symbol: str) -> bool:
        return symbol in self.state["discovered"].get(d, {})

    def snapshot_surge_decision(self, snapshot: Dict[str, Any], snapshot_date: str,
                                now_dt: datetime) -> Tuple[str, str, Optional[Dict[str, Any]]]:
        """Isolated OLD_A_SNAPSHOT_DERIVED_SURGE_V1 gate.

        Reuses the old-A F10/EVG implementation, but refuses to call it unless
        its ten-session input is already resident locally. This prevents the
        old fallback path from adding per-symbol history HTTP requests.
        The result is a separate snapshot-time variant; it is not fixed M+1.
        """
        symbol = str(snapshot.get("stock_id") or "")
        day = str(snapshot.get("date") or "")[:10]
        if not re.fullmatch(r"\d{4}", symbol) or day != snapshot_date:
            return "UNKNOWN", "SNAPSHOT_IDENTITY_OR_DATE_INVALID", None
        try:
            volume = float(snapshot.get("total_volume"))
            if not math.isfinite(volume) or volume < 0:
                return "UNKNOWN", "SNAPSHOT_VOLUME_INVALID", None
        except (TypeError, ValueError):
            return "UNKNOWN", "SNAPSHOT_VOLUME_INVALID", None
        if volume < 1000.0:
            return "FAIL", "CUMULATIVE_LOTS_BELOW_1000", {"cumulative_lots": volume}
        if not self.adapter.has_complete_f10_cache_only(symbol, snapshot_date):
            return "UNKNOWN", "F10_CACHE_MISS_NO_HISTORY_FALLBACK", None
        try:
            f10, avg5, prev1, _days = self.adapter.estimated_vr5_parts(
                symbol, snapshot_date, now_dt
            )
            if not all(math.isfinite(float(v)) and float(v) > 0 for v in (f10, avg5, prev1)):
                return "UNKNOWN", "F10_METRIC_UNDEFINED", None
            projected = volume / f10
            evg5 = projected / avg5
            evg_pct = (projected / prev1 - 1.0) * 100.0
            evg1 = 1.0 + evg_pct / 100.0
            metrics = {
                "symbol": symbol, "date": day, "cumulative_lots": volume,
                "estimated_vr5": evg5, "evg_pct": evg_pct, "evg1": evg1,
                "f10_fraction": f10, "prior5_average_lots": avg5,
                "previous_day_lots": prev1,
                "variant": "OLD_A_SNAPSHOT_DERIVED_SURGE_V1",
                "time_semantics": "SNAPSHOT_OBSERVATION; NOT_FIXED_M_PLUS_1",
            }
        except (AuditStop, OSError, sqlite3.Error, TypeError, ValueError, ZeroDivisionError) as exc:
            return "UNKNOWN", f"F10_OR_EVG_UNAVAILABLE:{type(exc).__name__}", None
        passed = evg5 >= 2.5 or evg1 >= 2.5
        return ("PASS", "OR_A_THRESHOLD_MET", metrics) if passed else ("FAIL", "OR_A_THRESHOLD_NOT_MET", metrics)


    def armed_info(self, d: str, symbol: str) -> Optional[Dict[str, Any]]:
        x = self.state["volume_armed"].get(d, {}).get(symbol)
        return x if isinstance(x, dict) else None

    def arm_volume(self, d: str, symbol: str, reasons: List[str],
                   raw_vr5: float, est_vr5: Optional[float]) -> Dict[str, Any]:
        existing = self.armed_info(d, symbol)
        if existing:
            return existing
        info = {
            "armed_at": now_tw().strftime("%H:%M:%S"),
            "reasons": list(reasons),
            "raw_vr5": round(raw_vr5, 4),
            "estimated_vr5": round(est_vr5, 4) if est_vr5 is not None else None,
        }
        self.state["volume_armed"].setdefault(d, {})[symbol] = info
        keys = sorted(self.state["volume_armed"].keys())
        for old in keys[:-10]:
            self.state["volume_armed"].pop(old, None)
        save_json_atomic(STATE_FILE, self.state)
        append_event({"ts": iso_now(), "type": "volume_armed",
                      "symbol": symbol, "date": d, **info})
        print(f"[A ARM] symbol={symbol} reasons={','.join(reasons)} "
              f"rawVR5={raw_vr5:.3f} estVR5={est_vr5 if est_vr5 is not None else 'NA'}",
              flush=True)
        return info

    def queue_entered_at(self, d: str, symbol: str) -> str:
        """Persistent FIFO timestamp: first time the stock became liquidity-eligible today."""
        dayq = self.state["queue_waiting"].setdefault(d, {})
        info = dayq.get(symbol)
        if isinstance(info, dict) and info.get("entered_at"):
            return str(info["entered_at"])
        entered = now_tw().isoformat(timespec="microseconds")
        dayq[symbol] = {"entered_at": entered}
        for old in sorted(self.state["queue_waiting"].keys())[:-10]:
            self.state["queue_waiting"].pop(old, None)
        save_json_atomic(STATE_FILE, self.state)
        return entered

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
        # Reuse legacy A handoff semantics for all routes:
        # mark success only after bridge_send returns; failures remain retryable.
        ack = self.bridge_send(payload)
        if self.layered_a_enabled:
            # In layered mode, HTTP transport success alone is not B acceptance.
            # A dry bridge or a malformed/negative B response must stay retryable.
            if not isinstance(ack, dict) or ack.get("http_status") != 200:
                raise RuntimeError("B_HANDOFF_ACK_MISSING")
            body = ack.get("body")
            expected_key = f"{snap_date}|{str(symbol).zfill(4)}"
            if not isinstance(body, dict) or body.get("ok") is not True or body.get("key") != expected_key:
                raise RuntimeError("B_HANDOFF_ACK_INVALID")
            if not any(body.get(k) is True for k in ("launched", "duplicate", "already_done")):
                raise RuntimeError("B_HANDOFF_NOT_ACCEPTED")
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
                if self.layered_a_enabled:
                    try:
                        parsed = json.loads(resp)
                    except Exception:
                        parsed = None
                    return {"http_status": r.status, "body": parsed}
        except Exception as e:
            # handoff 失敗不能先 dedupe；下輪要能重試。
            raise RuntimeError(f"Bridge handoff failed: {e}") from e

    def _layered_vcp_runtime(self):
        runtime = getattr(self, "vcp_scan_once_runtime", None)
        if runtime is None:
            from vcp_scan_once_adapter import VcpScanOnceRuntime
            runtime = VcpScanOnceRuntime(now_tw, self.state.get("layered_vcp_state", {}))
            self.vcp_scan_once_runtime = runtime
        return runtime

    def _layered_vcp_inputs(self, symbol: str, snap_date: str):
        """Resolve metadata/daily bars locally only; no ticker/history HTTP fallback."""
        adapter = self.adapter
        meta = getattr(adapter, "meta_cache", {}).get(symbol)
        if meta is None:
            meta = getattr(adapter, "f11_metadata_cache", {}).get(symbol)
        if not isinstance(meta, dict) or not self.selector.meta_ok(meta):
            return None, None, "VCP_METADATA_NOT_READY"
        try:
            bars = adapter.daily_history_local_ready(symbol, snap_date)
        except Exception as exc:
            return meta, None, f"VCP_LOCAL_HISTORY_ERROR:{type(exc).__name__}"
        if not isinstance(bars, list) or len(bars) < 60:
            return meta, None, "VCP_PRIOR_60_DAILY_BARS_NOT_READY"
        dates = [str(getattr(bar, "date", "")) for bar in bars]
        if dates != sorted(set(dates)) or any(day >= snap_date for day in dates):
            return meta, None, "VCP_HISTORY_IDENTITY_OR_CAUSAL_ORDER"
        return meta, bars, None

    @staticmethod
    def liquidity_minimum(dt: datetime) -> Optional[float]:
        hm = (dt.hour, dt.minute)
        if hm < (9, 1):
            return None
        if hm < (9, 10):
            return EARLY_VOLUME_MIN
        return REGULAR_VOLUME_MIN

    @staticmethod
    def queue_priority(raw_vr5: float, today_vol: float) -> int:
        # Lower rank runs first. Priority is recomputed from the latest snapshot,
        # so WAITING stocks can dynamically upgrade. FIFO is handled separately.
        if raw_vr5 >= RAW_VR5_MIN:
            return 0
        if today_vol >= 5000:
            return 1
        if today_vol >= 4000:
            return 2
        if today_vol >= 3000:
            return 3
        return 4

    def scan_once(self) -> List[Dict[str, Any]]:
        started = time.monotonic()
        snaps = self.adapter.snapshot()
        # Opt-in: filter recorded exceptions before VCP, SURGE and FLOW.
        if os.environ.get("A_SINGLE_STOCK_QUARANTINE", "0") == "1":
            from research.per_symbol_exception_policy_v1 import read_quarantined, check_systemic_health
            db_path = os.environ.get("A_SHARED_DAILY_DB", "/var/data/stock-alert/shared_history_stage_v1.sqlite3")
            quarantined = read_quarantined(db_path)
            import sqlite3
            with sqlite3.connect(Path(db_path).resolve().as_uri()+"?mode=ro", uri=True, timeout=3) as qdb:
                suspended = {str(r[0]) for r in qdb.execute("SELECT symbol FROM suspension_watch")}
                total = qdb.execute("SELECT COUNT(*) FROM fetch_status").fetchone()[0]
            excluded = quarantined | suspended
            check_systemic_health(total, len(excluded))
            if excluded:
                before = len(snaps)
                snaps = [r for r in snaps if str(r.get("stock_id") or "") not in excluded]
                print(f"[A QUARANTINE] excluded_symbols={len(excluded)} snapshot_removed={before-len(snaps)}", flush=True)
        print(f"[A DIAG] snapshot_done rows={len(snaps)}", flush=True)
        if not snaps:
            raise AuditStop("empty Fugle Snapshot")

        dates = {str(x.get("date") or "")[:10] for x in snaps if x.get("date")}
        if len(dates) != 1:
            raise AuditStop(f"Snapshot identity date mismatch: {sorted(dates)}")
        snap_date = next(iter(dates))
        now_dt = now_tw()

        if snap_date != now_dt.date().isoformat():
            raise AuditStop(f"stale Snapshot: snapshot={snap_date}, today={now_dt.date().isoformat()}")


        vol_min = self.liquidity_minimum(now_dt)
        if vol_min is None and not self.layered_a_enabled:
            print("[A WARMUP] 09:00: EVG/EstimatedVR5 disabled until 09:01", flush=True)
            return []

        # Pinned VCP watches start from 800 snapshot lots and remain independent
        # of FLOW's rising/liquidity/ARM gates. Existing watches, pending retries,
        # and active Pivot tracks continue even after any route has handed off.
        vcp_decisions: Dict[str, Dict[str, Any]] = {}
        layered_vcp_seconds = 0.0
        if self.layered_a_enabled:
            vcp_runtime = self._layered_vcp_runtime()
            vcp_t0 = time.monotonic()
            for row in snaps:
                symbol = str(row.get("stock_id") or "")
                if not self.selector.basic_code_ok(symbol):
                    continue
                volume = float(row.get("total_volume") or 0.0)
                should_track = (
                    volume >= 800
                    or vcp_runtime.has_pending(snap_date, symbol)
                    or vcp_runtime.has_watch(snap_date, symbol)
                    or vcp_runtime.has_active_track(symbol)
                )
                if not should_track:
                    continue
                meta, bars, reason = self._layered_vcp_inputs(symbol, snap_date)
                if reason:
                    vcp_decisions[symbol] = {"status": "UNKNOWN", "reason": reason}
                    append_event({"ts": iso_now(), "type": "vcp_unknown", "symbol": symbol,
                                  "date": snap_date, "reason": reason,
                                  "source_sha": "c1cc4c968c3288c32e167b52a01d34cc260cb02baac4ce7b6ef06f6f37298da7"})
                    continue
                prior5 = [float(bar.volume_zhang) for bar in bars[-5:] if float(bar.volume_zhang) >= 0]
                if len(prior5) != 5 or sum(prior5) <= 0:
                    reason = "VCP_PRIOR5_VOLUME_INVALID"
                    vcp_decisions[symbol] = {"status": "UNKNOWN", "reason": reason}
                    append_event({"ts": iso_now(), "type": "vcp_unknown", "symbol": symbol,
                                  "date": snap_date, "reason": reason})
                    continue
                raw_vr5 = volume / (sum(prior5) / 5.0)
                priority = self.queue_priority(raw_vr5, volume)
                decision = vcp_runtime.evaluate(row, bars, meta, raw_vr5, priority)
                vcp_decisions[symbol] = {
                    "status": "PASS" if decision.get("proposals") else "FAIL",
                    "reason": "PINNED_VCP_PENDING_OR_CONFIRMED_BREAKOUT" if decision.get("proposals") else "VCP_NOT_HANDOFF_READY",
                    "hit": (decision.get("proposals") or [None])[0],
                    "state": decision.get("vcp_state"), "watch": decision.get("watch"),
                }
                if decision.get("fire_event"):
                    append_event({"ts": iso_now(), "type": "vcp_fire", **decision["fire_event"]})
            layered_vcp_seconds = time.monotonic() - vcp_t0
            self.state["layered_vcp_state"] = vcp_runtime.export_state()
            save_json_atomic(STATE_FILE, self.state)

        # SURGE is evaluated from the same snapshot before any FLOW-only price/liquidity gate.
        # Prime cache-only F10 data once per scan; no per-symbol connection fanout or HTTP fallback.
        surge_decisions: Dict[str, Tuple[str, str, Optional[Dict[str, Any]], Dict[str, Any]]] = {}
        if self.layered_a_enabled and vol_min is not None:
            surge_symbols = [str(row.get("stock_id") or "") for row in snaps
                             if self.selector.basic_code_ok(str(row.get("stock_id") or ""))]
            prepare = getattr(self.adapter, "prepare_f10_cache_only", None)
            if callable(prepare):
                prepare(surge_symbols, snap_date)
            for row in snaps:
                symbol = str(row.get("stock_id") or "")
                if not self.selector.basic_code_ok(symbol) or self.already_sent(snap_date, symbol):
                    continue
                status, reason, metrics = self.snapshot_surge_decision(row, snap_date, now_dt)
                surge_decisions[symbol] = (status, reason, metrics, row)
                if status == "UNKNOWN":
                    append_event({"ts": iso_now(), "type": "surge_unknown", "symbol": symbol,
                                  "date": snap_date, "reason": reason, "variant": SURGE_VARIANT})

        # Dispatch by route precedence, before FLOW preparation can consume the
        # scan's handoff opportunity. FLOW's own prepared FIFO remains unchanged.
        selected: List[Dict[str, Any]] = []
        decided_symbols = set()
        attempted_symbols = set()  # no second route may retry a rejected handoff in the same scan
        if self.layered_a_enabled:
            for symbol, decision in vcp_decisions.items():
                hit = decision.get("hit")
                if decision.get("status") != "PASS" or not isinstance(hit, dict):
                    continue
                if self.already_sent(snap_date, symbol):
                    continue
                hit = dict(hit)
                hit.setdefault("name", next(
                    (row.get("name") for row in snaps if str(row.get("stock_id") or "") == symbol), symbol
                ))
                try:
                    handed = self.handoff_hit(hit, snap_date)
                except RuntimeError as exc:
                    handed = False
                    print(f"[A VCP HANDOFF RETRY NEXT SCAN] symbol={symbol} error={exc}", flush=True)
                attempted_symbols.add(symbol)
                if handed:
                    selected.append(hit)
                    decided_symbols.add(symbol)
                append_event({"ts": iso_now(), "type": "layered_vcp_handoff", "symbol": symbol,
                              "date": snap_date, "handed": bool(handed), "disposition": "VCP_FIRST"})

            for symbol, (status, _reason, metrics, row) in surge_decisions.items():
                if (status != "PASS" or symbol in decided_symbols or symbol in attempted_symbols
                        or self.already_sent(snap_date, symbol)
                        ):
                    continue
                metrics = metrics or {}
                hit = {
                    "code": symbol, "name": row.get("name") or symbol,
                    "todayVol": float(row.get("total_volume") or 0),
                    "volRatio": round(float(metrics.get("estimated_vr5") or 0), 4),
                    "chgPct": round(float(row.get("change_rate") or 0), 2),
                    "price": float(row.get("close") or 0), "vcpInfo": None,
                    "source": "SURGE", "estimatedVr5": metrics.get("estimated_vr5"),
                    "evgPct": metrics.get("evg_pct"), "surgeVariant": SURGE_VARIANT,
                    "timeSemantics": "SNAPSHOT_OBSERVATION; NOT_FIXED_M_PLUS_1",
                }
                try:
                    handed = self.handoff_hit(hit, snap_date)
                except RuntimeError as exc:
                    handed = False
                    print(f"[A SURGE HANDOFF RETRY NEXT SCAN] symbol={symbol} error={exc}", flush=True)
                attempted_symbols.add(symbol)
                if handed:
                    selected.append(hit)
                    decided_symbols.add(symbol)

        # Mother gates: common-stock/code universe + must be rising + time-dependent liquidity.
        candidates = [
            s for s in snaps
            if vol_min is not None
            and self.selector.basic_code_ok(s["stock_id"])
            and float(s.get("change_rate") or 0) > 0
            and float(s.get("total_volume") or 0) >= vol_min
            and not self.already_sent(snap_date, s["stock_id"])
        ]
        print(f"[A DIAG] first_gate_done candidates={len(candidates)} liquidity_min={vol_min}", flush=True)

        # Phase 1: metadata/history audit + dynamic priority.
        #
        # WAIT_DATA rule:
        # - completed background results are incorporated by the Scanner main thread;
        # - historical-D network I/O is never performed by the A main scan;
        # - a MISS is deferred while later READY candidates continue;
        # - first queue eligibility time is preserved across the defer.
        self.apply_wait_data_results()

        prepared = []
        for s in candidates:
            symbol = s["stock_id"]
            try:
                try:
                    meta = self.adapter.ticker(symbol)
                except RuntimeError as exc:
                    if F11_OFFLINE_STAGING_ENABLED and str(exc).startswith("F11_OFFLINE_MISS:"):
                        print(f"[A F11 OFFLINE MISS] symbol={symbol} deferred; no HTTP", flush=True)
                        continue
                    raise
                if not self.selector.meta_ok(meta):
                    continue

                record_a_scan_mother_identity(snap_date, symbol)
                entered_at = self.queue_entered_at(snap_date, symbol)

                bars = self.adapter.daily_history_local_ready(symbol, snap_date)
                if bars is None:
                    submitted = self.wait_data_worker.submit(symbol, snap_date)
                    print(
                        f"[A WAIT_DATA] symbol={symbol} date={snap_date} "
                        f"status={'QUEUED' if submitted else 'PENDING'} "
                        f"queue_entered_at={entered_at}",
                        flush=True,
                    )
                    continue

                prior5 = [b.volume_zhang for b in bars[-5:] if b.volume_zhang >= 0]
                if len(prior5) != 5:
                    raise AuditStop(f"{symbol} prior5 complete daily volume coverage !=5")
                avg5_daily = sum(prior5) / 5.0
                if avg5_daily <= 0:
                    raise AuditStop(f"{symbol} invalid prior5 daily average volume")
                today_vol = float(s.get("total_volume") or 0.0)
                raw_vr5 = today_vol / avg5_daily
                priority = self.queue_priority(raw_vr5, today_vol)
                qinfo = self.state["queue_waiting"].setdefault(snap_date, {}).setdefault(symbol, {"entered_at": entered_at})
                prev_priority = qinfo.get("shadow_last_priority")
                if prev_priority is None:
                    append_queue_shadow(snap_date, {
                        "type": "QUEUE_ENTER", "symbol": symbol,
                        "today_vol": today_vol, "raw_vr5": round(raw_vr5, 6),
                        "priority": priority, "queue_entered_at": entered_at,
                    })
                elif int(prev_priority) != int(priority):
                    append_queue_shadow(snap_date, {
                        "type": "TIER_UPGRADE" if int(priority) < int(prev_priority) else "TIER_CHANGE",
                        "symbol": symbol, "from_priority": int(prev_priority), "to_priority": int(priority),
                        "today_vol": today_vol, "raw_vr5": round(raw_vr5, 6),
                        "queue_entered_at": entered_at,
                    })
                qinfo["shadow_last_priority"] = int(priority)
                prepared.append((priority, entered_at, s, meta, bars, raw_vr5))
            except AuditStop:
                raise
            except Exception as e:
                append_event({"ts": iso_now(), "type": "candidate_error",
                              "symbol": symbol, "error": f"{type(e).__name__}: {e}"})

        # SHADOW ONLY: compare current production FIFO against same-tier latest-volume ordering.
        # IMPORTANT: candidate_volume_order is NEVER used for execution.
        control_order = sorted(prepared, key=lambda x: (x[0], x[1]))
        candidate_volume_order = sorted(
            prepared,
            key=lambda x: (x[0], -float(x[2].get("total_volume") or 0.0), x[1]),
        )
        control_rank = {x[2]["stock_id"]: i for i, x in enumerate(control_order, 1)}
        candidate_rank = {x[2]["stock_id"]: i for i, x in enumerate(candidate_volume_order, 1)}
        scan_id = now_tw().isoformat(timespec="microseconds")
        for x in control_order:
            p, entered_at, s0, _meta0, _bars0, raw0 = x
            sym0 = s0["stock_id"]
            cr = control_rank[sym0]
            vr = candidate_rank[sym0]
            append_queue_shadow(snap_date, {
                "type": "QUEUE_COMPARE", "scan_id": scan_id, "symbol": sym0,
                "today_vol": float(s0.get("total_volume") or 0.0),
                "raw_vr5": round(float(raw0), 6), "priority": int(p),
                "queue_entered_at": entered_at,
                "control_fifo_rank": cr, "candidate_volume_rank": vr,
                "rank_delta": cr - vr,
            })

        # PRODUCTION CONTROL UNCHANGED: SPECIAL > Q1 > Q2 > Q3 > Q4; same-tier persistent FIFO.
        prepared.sort(key=lambda x: (x[0], x[1]))

        # Phase 2: one waiting queue; running work is non-preemptive.
        for idx, (priority, entered_at, s, meta, bars, raw_vr5) in enumerate(prepared, 1):
            symbol = s["stock_id"]
            if self.layered_a_enabled and symbol in attempted_symbols:
                continue
            today_vol = float(s.get("total_volume") or 0.0)
            append_queue_shadow(snap_date, {
                "type": "PROCESS_START", "scan_id": scan_id, "symbol": symbol,
                "today_vol": today_vol, "raw_vr5": round(float(raw_vr5), 6),
                "priority": int(priority), "queue_entered_at": entered_at,
                "control_fifo_rank": control_rank.get(symbol),
                "candidate_volume_rank": candidate_rank.get(symbol),
            })
            try:
                armed = self.armed_info(snap_date, symbol)
                est_vr5 = None
                evg_pct = None

                f10_missing_no_vcp = False
                if not armed:
                    try:
                        f10, avg5_1m, prev1_1m, _fdays = self.adapter.estimated_vr5_parts(
                            symbol, snap_date, now_tw()
                        )
                    except AuditStop as exc:
                        # Only the explicit >2-session F10 miss takes this route.
                        # Malformed rows, causal mismatches, and other audits still STOP.
                        if "F10 DB incomplete:" not in str(exc):
                            raise
                        f10_missing_no_vcp = True
                        print(f"[A F10 MISS] symbol={symbol} NO_VCP evaluation; no bulk API", flush=True)
                    if not f10_missing_no_vcp:
                        projected = today_vol / f10
                        est_vr5 = projected / avg5_1m
                        evg_pct = (projected / prev1_1m - 1.0) * 100.0

                    reasons: List[str] = []
                    if not f10_missing_no_vcp:
                        if est_vr5 >= ESTIMATED_VR5_MIN:
                            reasons.append("EST_VR5_1P5")
                        if evg_pct >= EVG_MIN_PCT:
                            reasons.append("EVG_P50")

                    if reasons:
                        armed = self.arm_volume(snap_date, symbol, reasons, raw_vr5, est_vr5)
                        armed["evg_pct"] = round(evg_pct, 4)
                        self.state["volume_armed"].setdefault(snap_date, {})[symbol] = armed
                        save_json_atomic(STATE_FILE, self.state)
                        append_event({"ts": iso_now(), "type": "volume_anomaly",
                                      "symbol": symbol, "date": snap_date,
                                      "estimated_vr5": round(est_vr5, 4),
                                      "evg_pct": round(evg_pct, 4),
                                      "priority": "SPECIAL" if priority == 0 else f"Q{priority}"})

                if f10_missing_no_vcp:
                    # Preserve original NO_VCP price/MA20 requirements. Do not
                    # fabricate F10/EVG or classify insufficient MA20 as a hit.
                    chg = float(s.get("change_rate") or 0)
                    price = float(s.get("close") or 0)
                    ma20 = sum(b.close for b in bars[-20:]) / 20 if len(bars) >= 20 else 0
                    if len(bars) >= 20 and chg >= 2.5 and ma20 > 0 and price >= ma20:
                        hit = {
                            "code": symbol, "name": s.get("name") or symbol,
                            "todayVol": today_vol, "volRatio": round(raw_vr5, 2),
                            "chgPct": round(chg, 2), "price": price,
                            "vcpInfo": None, "source": "NO_VCP",
                            "ma20": round(ma20, 2),
                            "rawVr5": round(raw_vr5, 4),
                            "volumeTriggers": ["F10_INCOMPLETE_NO_VCP"],
                            "volumeArmedAt": None, "estimatedVr5": None,
                            "evgPct": None,
                            "queuePriority": "SPECIAL" if priority == 0 else f"Q{priority}",
                        }
                        selected.append(hit)
                        handed = self.handoff_hit(hit, snap_date)
                        print(f"[A F10 NO_VCP] symbol={symbol} handed={handed}", flush=True)
                    else:
                        print(f"[A F10 NO_VCP] symbol={symbol} original MA20/2.5pct gate not met", flush=True)
                    continue

                if not armed:
                    print(f"[A DIAG] candidate_done {idx}/{len(prepared)} symbol={symbol} "
                          f"priority={'SPECIAL' if priority==0 else 'Q'+str(priority)} anomaly=False", flush=True)
                    continue

                s_for_select = dict(s)
                armed_est = armed.get("estimated_vr5")
                s_for_select["_volume_display_ratio"] = float(armed_est) if armed_est is not None else raw_vr5
                if self.layered_a_enabled and hasattr(self.selector, "analyze_vcp"):
                    # Keep the original selector method byte-for-byte intact.
                    # During the candidate FLOW pass, suppress only its embedded
                    # VCP calculation; the pinned independent VCP pass above is
                    # the sole VCP handoff authority.
                    original_vcp = self.selector.analyze_vcp
                    had_instance_override = "analyze_vcp" in getattr(self.selector, "__dict__", {})
                    self.selector.analyze_vcp = lambda *_args, **_kwargs: {
                        "status": "not_formed", "breakoutTrack": None
                    }
                    try:
                        hit = self.selector.select_one(s_for_select, meta, bars)
                    finally:
                        if had_instance_override:
                            self.selector.analyze_vcp = original_vcp
                        else:
                            del self.selector.analyze_vcp
                else:
                    hit = self.selector.select_one(s_for_select, meta, bars)
                chosen = hit
                if chosen:
                    if chosen.get("source") != "SURGE":
                        chosen["rawVr5"] = round(raw_vr5, 4)
                        chosen["volumeTriggers"] = armed.get("reasons", [])
                        chosen["volumeArmedAt"] = armed.get("armed_at")
                        chosen["estimatedVr5"] = armed.get("estimated_vr5")
                        chosen["evgPct"] = armed.get("evg_pct")
                        chosen["queuePriority"] = "SPECIAL" if priority == 0 else f"Q{priority}"
                    selected.append(chosen)
                    handed = self.handoff_hit(chosen, snap_date)
                    decided_symbols.add(symbol)
                    print(f"[A HANDOFF] symbol={symbol} handed={handed} source={chosen['source']} "
                          f"priority={chosen.get('queuePriority')} estVR5={chosen.get('estimatedVr5')} EVG={chosen.get('evgPct')}", flush=True)
                else:
                    print(f"[A DIAG] candidate_done {idx}/{len(prepared)} symbol={symbol} "
                          f"anomaly=True structural=False", flush=True)
            except AuditStop:
                raise
            except Exception as e:
                append_event({"ts": iso_now(), "type": "candidate_error",
                              "symbol": symbol, "error": f"{type(e).__name__}: {e}"})

        elapsed = time.monotonic() - started
        print(f"[SCAN] {iso_now()} snapshot={len(snaps)} first_gate={len(candidates)} "
              f"prepared={len(prepared)} selected={len(selected)} elapsed={elapsed:.2f}s "
              f"queue=SPECIAL>Q1>Q2>Q3>Q4 same-tier=FIFO", flush=True)
        return selected


def run_self_test() -> None:
    # 純邏輯測試，不打 Fugle、不打 Bridge、不讀寫 production track。
    print("=" * 88)
    print("A SCANNER V2.4 | SELF TEST")
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
        "_volume_display_ratio": 1.50,
    }
    meta = {"market": "TSE", "securityType": "01", "industry": "26"}
    hit = s.select_one(stock, meta, bars, inject_snapshot_today=False)
    s.track = old_track
    assert hit is not None and hit["source"] == "NO_VCP", hit
    assert hit["volRatio"] == 1.5, hit

    stock2 = dict(stock)
    stock2["change_rate"] = 2.49
    hit2 = s.select_one(stock2, meta, bars, inject_snapshot_today=False)
    assert hit2 is None

    stock3 = dict(stock)
    stock3["total_volume"] = 3999
    assert s.select_one(stock3, meta, bars, inject_snapshot_today=False) is not None

    # Volume gating now belongs to Scanner's persistent ANY-1 watchlist,
    # not StrongSelector. Structural selector remains unchanged after arming.
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
    print("[PASS] liquidity: 09:01-09:09 >=4000; 09:10+ >=2000")
    print("[PASS] anomaly: EstimatedVR5>=1.5 OR EVG>=+50%; rawVR5>=1.5 SPECIAL only")
    assert Scanner.queue_priority(1.5, 2000) == 0
    assert Scanner.queue_priority(1.49, 5000) == 1
    assert Scanner.queue_priority(1.49, 4000) == 2
    assert Scanner.queue_priority(1.49, 3000) == 3
    assert Scanner.queue_priority(1.49, 2000) == 4
    print("[PASS] queue: SPECIAL > Q1 > Q2 > Q3 > Q4; same-tier persistent FIFO; dynamic upgrade")
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

    try:
        initialize_state_paths()
        key = fugle_key()
        adapter = FugleAdapter(key)
        scanner = Scanner(adapter, args.bridge_url)
    except AuditStop as e:
        print("AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL")
        print(str(e))
        return 2

    print("=" * 88)
    print("FUGLE A SCANNER V2.4 | ABNORMAL-VOLUME HANDOFF")
    print("=" * 88)
    print(f"interval       = {args.interval:g}s")
    print(f"bridge         = {args.bridge_url or 'OFF / DRY RUN'}")
    print("market         = TSE + OTC | COMMONSTOCK")
    print("production     = A DISCOVERY ONLY | B DOES P1/A/B/C")
    print("anomaly        = EstimatedVR5>=1.5 OR EVG>=+50%")
    print("liquidity      = 09:01-09:09 >=4000 | 09:10+ >=2000 | rawVR5>=1.5 SPECIAL priority")
    print(f"output         = {OUTDIR}")
    print(f"queue shadow   = {SHADOW_AUDIT_ROOT} | AUDIT ONLY | production FIFO unchanged")
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
            # Stage-only safety: do not carry yesterday's verified DB watermark
            # into a new trading day. Exit so parent reruns calendar + DB preflight.
            verified_day = os.environ.get("A_VERIFIED_SNAPSHOT_DAY", "").strip()
            if verified_day:
                from a_session_rollover_guard_v1 import assert_a_session_identity, ASessionRolloverError
                try:
                    assert_a_session_identity(dt.date().isoformat(), verified_day,
                                              os.environ.get("A_LAST_COMPLETED_SESSION", ""))
                except ASessionRolloverError as exc:
                    print(f"[A SESSION ROLLOVER STOP] {exc}; NO PRODUCTION SIGNAL", flush=True)
                    return 2
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
