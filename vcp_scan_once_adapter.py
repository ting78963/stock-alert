"""Isolated scan_once adapter around the pinned VCP AST fragment.

The VCP calculations/state fragment are compiled from the pinned source carried
by vcp_a.py. Only the caller's FLOW-candidate gate is widened for this explicit
integration requirement: >=800 lots (or a pending retry) is evaluated even if
the snapshot is flat/down. No market/API/bridge/LINE calls are made here.
"""
from __future__ import annotations

import ast
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


def _extract_scan_once_fragment(ns):
    tree = ast.parse(vcp_a.SOURCE_TEXT)
    scan = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "scan_once")
    body = next(
        n.body for n in ast.walk(scan)
        if isinstance(n, ast.Try) and any(
            isinstance(x, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "vcp_state" for t in x.targets)
            for x in n.body
        )
    )
    start = next(
        i for i, n in enumerate(body)
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "vcp_state" for t in n.targets)
    )
    fragment = copy.deepcopy(body[start:start + 4])
    assert len(fragment) == 4 and isinstance(fragment[-1], ast.If)
    # The source's formulas remain byte-for-byte AST-derived. The integration
    # contract moves VCP observation outside FLOW's rise/liquidity/ARM gates.
    fragment[-1].test = ast.parse("today_vol >= 800 or has_pending_vcp", mode="eval").body
    fn = ast.parse(
        "def extracted_scan_once(self,s,snap_date,bars,raw_vr5,priority):\n"
        " symbol=s['stock_id']\n"
        " today_vol=float(s.get('total_volume') or 0.0)\n"
        " selected=[]\n"
        " for _ in (None,):\n  pass\n"
        " return dict(vcp_state=vcp_state,selected=selected)\n"
    ).body[0]
    fn.body[-2].body = fragment
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<PINNED_VCP_SCAN_ONCE_FRAGMENT>", "exec"), ns)
    return ns["extracted_scan_once"]


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
        self.extracted = _extract_scan_once_fragment(self.ns)
        self.histories = {}
        self.metadata = {}
        self.engine = vcp_a.engine(self.ns, clock, self.histories, self.metadata)
        self.engine.state = copy.deepcopy(persisted_state.get("watch_state", {
            "discovered": {}, "volume_armed": {}, "queue_waiting": {}, "vcp_near_watch": {}
        }) if isinstance(persisted_state, dict) else {
            "discovered": {}, "volume_armed": {}, "queue_waiting": {}, "vcp_near_watch": {}
        })
        self.engine.state.setdefault("vcp_near_watch", {})
        self.engine.selector.track = copy.deepcopy(persisted_state.get("pivot_track", {}) if isinstance(persisted_state, dict) else {})
        self.fire_ids = copy.deepcopy(persisted_state.get("fire_ids", {}) if isinstance(persisted_state, dict) else {})

    def has_pending(self, day, symbol):
        entry = self.engine.state.get("vcp_near_watch", {}).get(day, {}).get(symbol)
        return isinstance(entry, dict) and isinstance(entry.get("pending_breakout"), dict)

    def has_watch(self, day, symbol):
        return isinstance(self.engine.state.get("vcp_near_watch", {}).get(day, {}).get(symbol), dict)

    def has_active_track(self, symbol):
        return isinstance(self.engine.selector.track.get(symbol), dict)

    def evaluate(self, row, bars, metadata, raw_vr5, priority):
        day = str(row.get("date") or "")[:10]
        symbol = str(row.get("stock_id") or "")
        self.metadata[symbol] = copy.deepcopy(metadata)
        self.histories[day + "|" + symbol] = [
            (b.date, float(b.close), float(b.volume_zhang)) for b in bars
        ]
        self.engine.adapter.rows = [copy.deepcopy(row)]
        proposals = []
        self.engine.handoff_hit = lambda hit, _day: (proposals.append(copy.deepcopy(hit)) or True)
        result = self.extracted(self.engine, row, day, bars, raw_vr5, priority)
        vcp_state = result.get("vcp_state")
        watch = self.engine.state.get("vcp_near_watch", {}).get(day, {}).get(symbol)
        track = self.engine.selector.track.get(symbol)
        fire = None
        if proposals:
            identity = {
                "day": day, "symbol": symbol,
                "pivot": (watch or {}).get("pivot", (track or {}).get("pivot")),
                "pending": copy.deepcopy((watch or {}).get("pending_breakout")),
                "source_sha": PINNED_VCP_SHA256,
            }
            fire_id = "vcp-fire-" + hashlib.sha256(
                json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if fire_id not in self.fire_ids:
                self.fire_ids[fire_id] = True
                fire = {
                    "event_id": fire_id, "kind": "🔥 VCP", "day": day,
                    "symbol": symbol, "original_pending": copy.deepcopy(identity["pending"]),
                    "watch": copy.deepcopy(watch), "vcp": copy.deepcopy(vcp_state),
                    "hit": copy.deepcopy(proposals[0]), "observed_at": self.manager.now(),
                    "received_at": None, "available_at": None,
                    "provenance": "SYNTHETIC_TEST_CLOCK_OR_UNVERIFIED_SNAPSHOT_RECEIPT",
                }
        self.last_decision = {
            "vcp_state": copy.deepcopy(vcp_state), "watch": copy.deepcopy(watch),
            "pivot_track": copy.deepcopy(track), "proposals": copy.deepcopy(proposals),
            "fire_event": copy.deepcopy(fire),
        }
        return {
            "vcp_state": copy.deepcopy(vcp_state), "watch": copy.deepcopy(watch),
            "pivot_track": copy.deepcopy(track), "proposals": proposals,
            "fire_event": fire, "handoff_ready": bool(proposals),
        }

    def export_state(self):
        return {
            "watch_state": copy.deepcopy(self.engine.state),
            "pivot_track": copy.deepcopy(self.engine.selector.track),
            "fire_ids": copy.deepcopy(self.fire_ids),
        }
