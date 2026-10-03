# -*- coding: utf-8 -*-
"""PHASE 1 audit-only FAST Runner overlay.

Imports the current B Runner unchanged and overrides only canonical-dirty tracking
and completed-minute scheduling. This file is NOT wired into production_worker.
No signal/threshold/recognition implementation is changed.
"""
from __future__ import annotations
import runpy
from pathlib import Path

BASE=Path(__file__).resolve().parent
SOURCE=BASE/"fugle_b_live_runner_v2_p1_final.py"
_m=runpy.run_path(str(SOURCE),run_name="__b_runner_fast_audit_base__")
BaseRunner=_m["Runner"]
nt=_m["nt"]; EPS=_m["EPS"]; completed_cutoff=_m["completed_cutoff"]

class Runner(BaseRunner):
    def __init__(self,*args,**kwargs):
        # Initialize scheduler state before BaseRunner work so the overlay is
        # safe even if future initialization paths merge canonical rows.
        self._dirty_minutes=set()
        self._last_completed_through=None
        self.fast_completed_checks=0
        self.fast_completed_evals=0
        self.fast_completed_skips=0
        super().__init__(*args,**kwargs)

    def merge(self,rows,source):
        add=chg=dup=0
        changed_minutes=set()
        for r in rows:
            t=nt(r["minute"])
            z={"date":self.date,"stock_id":self.sid,"minute":t,
               "open":float(r["open"]),"high":float(r["high"]),"low":float(r["low"]),
               "close":float(r["close"]),"volume":float(r["volume"])}
            old=self.rows.get(t)
            if old is None:
                self.rows[t]=z; add+=1; changed_minutes.add(t)
            elif all(abs(float(old[k])-float(z[k]))<=EPS for k in ("open","high","low","close","volume")):
                dup+=1
            else:
                self.rows[t]=z; chg+=1; changed_minutes.add(t)
        if source=="ws":
            self.ws_new+=add; self.ws_changed+=chg
        self._dirty_minutes.update(changed_minutes)
        self.audit_canonical("merge-"+source); self.save_canonical()
        return add,chg,dup

    def _mark_evaluated_through(self,through):
        through=nt(through)
        self._last_completed_through=through
        self._dirty_minutes={k for k in self._dirty_minutes if k>through}

    def evaluate_completed(self,origin):
        self.fast_completed_checks+=1
        cut=completed_cutoff()
        eligible=[k for k in self.rows if k<=cut]
        if not eligible:return
        through=max(eligible)
        causal_dirty=any(k<=through for k in self._dirty_minutes)
        if through==self._last_completed_through and not causal_dirty:
            self.fast_completed_skips+=1
            return
        self.evaluate(through,origin)
        self._mark_evaluated_through(through)
        self.fast_completed_evals+=1

    def rest_reconcile(self,label):
        # Preserve current BaseRunner REST/startup/reconnect semantics exactly,
        # including forced evaluate. Only mark the successfully replayed causal
        # range clean afterward so the next clock tick can dedupe it.
        self.rest_reconciles+=1
        rows=self.m["adapt"](self.m["fetch"](self.key,self.sid,self.date),self.date,self.sid)
        today=_m["now_tpe"]().strftime("%Y-%m-%d")
        if label=="startup":
            if self.date==today:
                completed=completed_cutoff()
                cut=self.disc if _m["ma"](self.disc)<=_m["ma"](completed) else completed
            else:
                cut=self.disc
            rows=[r for r in rows if nt(r["minute"])<=cut]
        elif self.date==today:
            cut=completed_cutoff()
            rows=[r for r in rows if nt(r["minute"])<=cut]
        a,c,d=self.merge(rows,"rest")
        if not self.rows:_m["stop"](f"REST {label}: no canonical rows")
        through=max(self.rows)
        print(f"[REST {label}] input={len(rows)} add={a} changed={c} exact_dup={d} canonical={len(self.rows)} through={through}")
        if label=="startup":
            self._notify_if_recognized(self.sig,"ABC")
            self._notify_if_recognized(self.p1sig,"P1")
        self.evaluate(through,label)
        self._mark_evaluated_through(through)

if __name__=="__main__":
    raise SystemExit("AUDIT OVERLAY ONLY: import Runner from this module; do not run directly.")
