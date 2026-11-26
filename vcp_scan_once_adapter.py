"""Isolated adapter using the pinned original VCP calculation directly.

The source-pinned StrongSelector.analyze_vcp remains the sole calculation and
Pivot-tracking implementation. The former 800-lot, watch, and pending gates do
not control handoff: only the original confirmed ``just_broke`` result can
propose a B handoff. No market/API/bridge/LINE calls are made here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIN_RELATIVE = Path("research") / "vcp_integration_audit_lab_20261018" / "scanner_7413a49.py.txt"
ROOT = next((p for p in (_HERE, *_HERE.parents) if (p / _PIN_RELATIVE).is_file()), None)
if ROOT is None:
    raise RuntimeError("PINNED_VCP_ROOT_NOT_FOUND")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import vcp_a

PINNED_VCP_SHA256 = "c1cc4c968c3288c32e167b52a01d34cc260cb02baac4ce7b6ef06f6f37298da7"
PINNED_VCP_FILE = ROOT / "research" / "vcp_integration_audit_lab_20261018" / "scanner_7413a49.py.txt"


class _ManagerClock:
    def __init__(self, clock):
        self._clock = clock
        self.high_seq = {}
        self.submitted = []

    def now(self):
        return self._clock().isoformat(timespec="seconds")

    def submit(self, candidate):
        self.submitted.append(candidate)


class VcpScanOnceRuntime:
    """Stateful isolated runner for the source-pinned VCP scan fragment."""

    def __init__(self, clock, persisted_state=None):
        if hashlib.sha256(PINNED_VCP_FILE.read_bytes()).hexdigest() != PINNED_VCP_SHA256:
            raise RuntimeError("PINNED_VCP_SOURCE_SHA_MISMATCH")
        self.clock = clock
        self.manager = _ManagerClock(clock)
        self.ns = vcp_a.namespace("layered_vcp_scan_once_" + str(id(self)))
        # The original analyzer consumes its inputs directly. Keep no per-scan
        # mirror of the entire market's daily history in this runtime.
        self.engine = vcp_a.engine(self.ns, clock, {}, {})
        self.engine.state = copy.deepcopy(persisted_state.get("watch_state", {
            "discovered": {}, "volume_armed": {}, "queue_waiting": {}, "vcp_near_watch": {}
        }) if isinstance(persisted_state, dict) else {
            "discovered": {}, "volume_armed": {}, "queue_waiting": {}, "vcp_near_watch": {}
        })
        self.engine.state.setdefault("vcp_near_watch", {})
        self.engine.selector.track = copy.deepcopy(persisted_state.get("pivot_track", {}) if isinstance(persisted_state, dict) else {})
        self.fire_ids = copy.deepcopy(persisted_state.get("fire_ids", {}) if isinstance(persisted_state, dict) else {})
        self.handoff_event_ids = copy.deepcopy(
            persisted_state.get("handoff_event_ids", {}) if isinstance(persisted_state, dict) else {}
        )

    def has_pending(self, day, symbol):
        entry = self.engine.state.get("vcp_near_watch", {}).get(day, {}).get(symbol)
        return isinstance(entry, dict) and isinstance(entry.get("pending_breakout"), dict)

    def has_watch(self, day, symbol):
        return isinstance(self.engine.state.get("vcp_near_watch", {}).get(day, {}).get(symbol), dict)

    def has_active_track(self, symbol):
        return isinstance(self.engine.selector.track.get(symbol), dict)

    def has_handoff_event(self, event_id):
        return bool(event_id and self.handoff_event_ids.get(str(event_id)))

    def mark_handoff_event(self, event_id):
        if event_id:
            self.handoff_event_ids[str(event_id)] = True

    def evaluate(self, row, bars, metadata, raw_vr5, priority):
        day = str(row.get("date") or "")[:10]
        symbol = str(row.get("stock_id") or "")
        empty = {"vcp_state": None, "watch": None, "pivot_track": None,
                 "proposals": [], "fire_event": None, "handoff_ready": False}
        if not day or not symbol or (metadata.get("symbol") and metadata["symbol"] != symbol):
            return {**empty, "status": "UNKNOWN", "reason": "VCP_IDENTITY_MISSING_OR_MISMATCH"}
        if not isinstance(bars, list) or len(bars) < 29:
            return {**empty, "status": "UNKNOWN", "reason": "VCP_PRIOR_29_DAILY_BARS_NOT_READY"}
        dates = [str(getattr(bar, "date", "")) for bar in bars]
        if dates != sorted(set(dates)) or any(d >= day for d in dates):
            return {**empty, "status": "UNKNOWN", "reason": "VCP_HISTORY_IDENTITY_OR_CAUSAL_ORDER"}
        try:
            current_close = float(row["close"])
            today_vol = float(row["total_volume"])
            if not (current_close > 0 and today_vol >= 0):
                raise ValueError("invalid snapshot values")
        except (KeyError, TypeError, ValueError):
            return {**empty, "status": "UNKNOWN", "reason": "VCP_SNAPSHOT_PRICE_OR_VOLUME_INVALID"}

        closes = [float(bar.close) for bar in bars] + [current_close]
        vols = [float(bar.volume_zhang) for bar in bars] + [today_vol]
        vcp_state = self.engine.selector.analyze_vcp(closes, vols, symbol, dates + [day])
        # justBroke is the original conjunction of price + 1.4x volume; the
        # original ``contracting`` result additionally requires the contraction
        # structure. Status labels such as trending_up describe breakout age,
        # not the three confirmation conditions requested for this route.
        confirmed = bool(vcp_state.get("justBroke")) and bool(vcp_state.get("contracting"))
        watch = self.engine.state.get("vcp_near_watch", {}).get(day, {}).get(symbol)
        track = self.engine.selector.track.get(symbol)
        fire = None
        proposals = []
        hit = None
        if confirmed:
            hit = {
                "code": symbol,
                "name": str(row.get("name") or symbol),
                "todayVol": today_vol,
                "volRatio": round(float(raw_vr5), 2),
                "chgPct": round(float(row.get("change_rate") or 0.0), 2),
                "price": current_close,
                "vcpInfo": {"type": "broke"},
                "source": "VCP",
                "rawVr5": round(float(raw_vr5), 4),
                "queuePriority": "SPECIAL" if int(priority) == 0 else f"Q{int(priority)}",
            }
            proposals.append(hit)
            active_track = self.engine.selector.track.get(symbol)
            pivot = float(vcp_state.get("pivot") or 0.0)
            track_breakout_date = (
                str(active_track.get("breakoutDate"))
                if isinstance(active_track, dict)
                and float(active_track.get("pivot") or 0.0) == pivot
                and active_track.get("breakoutDate") else ""
            )
            break_days = max(1, int(vcp_state.get("breakDays") or 1))
            derived_breakout_date = dates[max(0, len(dates) - break_days)]
            breakout_date = track_breakout_date or derived_breakout_date
            identity = {
                "symbol": symbol,
                "pivot": pivot,
                "breakout_date": breakout_date,
                "source_sha": PINNED_VCP_SHA256,
            }
            fire_id = "vcp-fire-" + hashlib.sha256(
                json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            hit["vcpEventId"] = fire_id
            if fire_id not in self.fire_ids:
                self.fire_ids[fire_id] = True
                fire = {
                    "event_id": fire_id, "kind": "🔥 VCP", "day": day,
                    "symbol": symbol, "original_pending": None,
                    "watch": copy.deepcopy(watch), "vcp": copy.deepcopy(vcp_state),
                    "hit": copy.deepcopy(hit), "observed_at": self.manager.now(),
                    "received_at": None, "available_at": None,
                    "provenance": "SNAPSHOT_OBSERVATION; SOURCE_RECEIVE_TIME_UNAVAILABLE",
                }
        self.last_decision = {
            "vcp_state": copy.deepcopy(vcp_state), "watch": copy.deepcopy(watch),
            "pivot_track": copy.deepcopy(track), "proposals": copy.deepcopy(proposals),
            "fire_event": copy.deepcopy(fire), "confirmed_breakout": confirmed,
        }
        return {
            "status": "PASS" if confirmed else "FAIL",
            "reason": "ORIGINAL_CONFIRMED_BREAKOUT" if confirmed else "VCP_NOT_CONFIRMED_BREAKOUT",
            "vcp_state": copy.deepcopy(vcp_state), "watch": copy.deepcopy(watch),
            "pivot_track": copy.deepcopy(track), "proposals": proposals,
            "fire_event": fire, "handoff_ready": bool(proposals),
        }

    def export_state(self):
        return {
            "watch_state": copy.deepcopy(self.engine.state),
            "pivot_track": copy.deepcopy(self.engine.selector.track),
            "fire_ids": copy.deepcopy(self.fire_ids),
            "handoff_event_ids": copy.deepcopy(self.handoff_event_ids),
        }
