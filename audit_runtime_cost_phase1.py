# -*- coding: utf-8 -*-
"""
PHASE 1 | RUNTIME COST AUDIT HARNESS | READ ONLY

Purpose
-------
Measure production A/B hot-path runtime without changing production files,
signal rules, recognition minutes, canonical data, or notification behavior.

This first harness deliberately focuses on B duplicate completed-minute work,
because production clock_loop calls evaluate_completed() once per second.
It monkey-patches methods only inside this audit process.

Safety
------
- Does NOT edit production files.
- Does NOT send LINE.
- Does NOT write into production state.
- Does NOT change signal/gate thresholds.
- Intended for local/shadow execution only.

Estimated runtime: seconds for --self-test; otherwise depends on supplied shadow run.
Main bottleneck: the underlying B replay/evaluation being measured.
"""
from __future__ import annotations

import argparse
import json
import runpy
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
BR = BASE / "fugle_b_live_runner_v2_p1_final.py"


class AuditStop(RuntimeError):
    pass


class RuntimeAudit:
    def __init__(self):
        self.completed_checks = 0
        self.evaluate_calls = 0
        self.evaluate_ms = []
        self.through_counts = Counter()
        self.origin_counts = Counter()
        self.last_through = None
        self.unique_transitions = 0

    def observe_completed_check(self, through, origin):
        self.completed_checks += 1
        if through is not None:
            through = str(through)
            self.through_counts[through] += 1
            if through != self.last_through:
                self.unique_transitions += 1
                self.last_through = through
        self.origin_counts[str(origin)] += 1

    def observe_evaluate(self, through, origin, elapsed_ms):
        self.evaluate_calls += 1
        self.evaluate_ms.append(float(elapsed_ms))

    def report(self):
        repeated_checks = sum(max(0, n - 1) for n in self.through_counts.values())
        total_with_through = sum(self.through_counts.values())
        duplicate_ratio = repeated_checks / total_with_through if total_with_through else 0.0
        vals = self.evaluate_ms
        return {
            "completed_check_calls": self.completed_checks,
            "checks_with_through": total_with_through,
            "unique_through_values": len(self.through_counts),
            "unique_through_transitions": self.unique_transitions,
            "duplicate_same_through_checks": repeated_checks,
            "duplicate_same_through_ratio": duplicate_ratio,
            "evaluate_calls": self.evaluate_calls,
            "evaluate_total_ms": sum(vals),
            "evaluate_avg_ms": statistics.fmean(vals) if vals else 0.0,
            "evaluate_max_ms": max(vals) if vals else 0.0,
            "origin_counts": dict(self.origin_counts),
        }


def install_b_observer(Runner):
    """Observation-only monkey patch. Return audit object + originals."""
    audit = RuntimeAudit()
    original_completed = Runner.evaluate_completed
    original_evaluate = Runner.evaluate

    def observed_evaluate(self, through, origin):
        t0 = time.perf_counter()
        try:
            return original_evaluate(self, through, origin)
        finally:
            audit.observe_evaluate(through, origin, (time.perf_counter() - t0) * 1000.0)

    def observed_completed(self, origin):
        cut = self.__class__.__module__  # no semantic use; prevents accidental optimization assumptions
        del cut
        # Reproduce only the observation of what the original method will see.
        # Do not short-circuit duplicates: original production behavior must run.
        try:
            module_globals = original_completed.__globals__
            completed_cutoff = module_globals["completed_cutoff"]
            c = completed_cutoff()
            eligible = [k for k in self.rows if k <= c]
            through = max(eligible) if eligible else None
        except Exception:
            through = None
        audit.observe_completed_check(through, origin)
        return original_completed(self, origin)

    Runner.evaluate = observed_evaluate
    Runner.evaluate_completed = observed_completed
    return audit, original_completed, original_evaluate


def self_test():
    """No network, no production files written, no Runner construction."""
    a = RuntimeAudit()
    for _ in range(3):
        a.observe_completed_check("10:14:00", "clock")
    a.observe_completed_check("10:15:00", "clock")
    a.observe_evaluate("10:14:00", "clock", 10.0)
    a.observe_evaluate("10:14:00", "clock", 20.0)
    a.observe_evaluate("10:15:00", "clock", 30.0)
    r = a.report()
    assert r["completed_check_calls"] == 4
    assert r["unique_through_values"] == 2
    assert r["duplicate_same_through_checks"] == 2
    assert abs(r["duplicate_same_through_ratio"] - 0.5) < 1e-12
    assert r["evaluate_calls"] == 3
    assert abs(r["evaluate_total_ms"] - 60.0) < 1e-12
    assert abs(r["evaluate_avg_ms"] - 20.0) < 1e-12
    print("[PASS] runtime counter arithmetic")
    print("[PASS] duplicate-through accounting")
    print("[PASS] no network / no production write / no LINE")
    print(json.dumps(r, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--load-b", action="store_true", help="Load B module and verify observation patch can be installed; does not construct a Runner.")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    if args.load_b:
        if not BR.is_file():
            raise AuditStop(f"missing B runner: {BR}")
        m = runpy.run_path(str(BR), run_name="__phase1_runtime_audit__")
        Runner = m["Runner"]
        audit, original_completed, original_evaluate = install_b_observer(Runner)
        if Runner.evaluate_completed is original_completed or Runner.evaluate is original_evaluate:
            raise AuditStop("observer installation failed")
        print("[PASS] B module loaded")
        print("[PASS] observation-only monkey patch installed in audit process")
        print("NO RUNNER CONSTRUCTED | NO NETWORK | NO LINE | NO PRODUCTION WRITE")
        print(json.dumps(audit.report(), ensure_ascii=False, indent=2))
        return

    ap.error("choose --self-test or --load-b")


if __name__ == "__main__":
    main()
