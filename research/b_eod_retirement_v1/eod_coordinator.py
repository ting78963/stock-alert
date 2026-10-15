# -*- coding: utf-8 -*-
"""B EOD lifecycle coordination, research only. No production import or side effects.

This module deliberately does NOT fetch REST, send LINE, or mutate persistent state.
An integration adapter must verify final REST bars, unchanged signal evaluation and
notification state before calling complete(). A failed check leaves the runner held.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any

class Phase(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"

@dataclass(frozen=True)
class Snapshot:
    phase: Phase
    pending_launches: int
    active: int
    held: int
    completed: int

class EODCoordinator:
    def __init__(self, day: str):
        self.day = day
        self._lock = RLock()
        self.phase = Phase.OPEN
        self._launching: set[str] = set()
        self._active: dict[str, Any] = {}
        self._held: dict[str, str] = {}
        self._completed: set[str] = set()

    def _check_key(self, key: str) -> None:
        if not key.startswith(self.day + "|"):
            raise ValueError("day mismatch: " + key)

    def claim(self, key: str) -> bool:
        self._check_key(key)
        with self._lock:
            if self.phase is not Phase.OPEN:
                return False
            if key in self._launching or key in self._active or key in self._completed:
                return False
            self._launching.add(key)
            return True

    def publish(self, key: str, runner: Any) -> bool:
        self._check_key(key)
        with self._lock:
            if key not in self._launching:
                raise RuntimeError("publish without claim")
            self._launching.remove(key)
            if self.phase is not Phase.OPEN:
                return False
            self._active[key] = runner
            return True

    def abort(self, key: str) -> None:
        self._check_key(key)
        with self._lock:
            self._launching.discard(key)

    def begin_close(self) -> Snapshot:
        with self._lock:
            if self.phase is Phase.OPEN:
                self.phase = Phase.CLOSING
            return self.snapshot()

    def hold(self, key: str, reason: str) -> None:
        self._check_key(key)
        if not reason:
            raise ValueError("hold requires reason")
        with self._lock:
            if key not in self._active:
                raise RuntimeError("cannot hold unknown runner")
            self._held[key] = reason

    def complete(self, key: str, *, queue_drained: bool, worker_exited: bool,
                 final_rest_verified: bool, final_evaluation_ok: bool,
                 notification_settled: bool, persistence_ok: bool) -> bool:
        """All evidence must be independently supplied by integration; never infer."""
        self._check_key(key)
        with self._lock:
            if self.phase is not Phase.CLOSING:
                raise RuntimeError("complete outside closing phase")
            if key not in self._active:
                raise RuntimeError("complete unknown runner")
            checks = {
                "queue_drained": queue_drained,
                "worker_exited": worker_exited,
                "final_rest_verified": final_rest_verified,
                "final_evaluation_ok": final_evaluation_ok,
                "notification_settled": notification_settled,
                "persistence_ok": persistence_ok,
            }
            failed = [k for k, ok in checks.items() if ok is not True]
            if failed:
                self._held[key] = ",".join(failed)
                return False
            del self._active[key]
            self._held.pop(key, None)
            self._completed.add(key)
            return True

    def finalize(self) -> bool:
        with self._lock:
            if self.phase is Phase.CLOSED:
                return True
            if self.phase is not Phase.CLOSING:
                raise RuntimeError("finalize before begin_close")
            if self._launching or self._active:
                return False
            self.phase = Phase.CLOSED
            return True

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(self.phase, len(self._launching),
                            len(self._active), len(self._held), len(self._completed))
