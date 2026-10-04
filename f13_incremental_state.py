# -*- coding: utf-8 -*-
# AUTO-GENERATED FROM CERTIFIED F13 AUDITORS. DO NOT HAND-EDIT.
from __future__ import annotations
import copy, math
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

EPS=1e-9

def nt(x):
    s=str(x)
    if len(s)>=8: return s[:8]
    if len(s)==5: return s+":00"
    return s

def stop(msg):
    raise RuntimeError("F13 STATE STOP | "+str(msg))

BUILD_ATTACK=None
def bind_attack_builder(fn):
    global BUILD_ATTACK
    BUILD_ATTACK=fn

@dataclass
class FastAttackState:
    key: float
    prev_close: float
    completed: list[dict] = field(default_factory=list)
    in_attack: bool = False
    attack_bars: list[dict] = field(default_factory=list)
    last_minute: str | None = None

    @staticmethod
    def bar_dict(row) -> dict:
        return {
            "time": str(row["time"]),
            "open": float(row["open"] or 0),
            "high": float(row["high"] or 0),
            "low": float(row["low"] or 0),
            "close": float(row["close"] or 0),
            "volume": int(row["volume"] or 0),
        }

    def step(self, row) -> None:
        t = nt(row["time_str"])
        if self.last_minute is not None and t <= self.last_minute:
            stop(f"FAST Attack non-increasing input: {t} <= {self.last_minute}")

        b = self.bar_dict(row)
        bar_high = b["high"]
        bar_close = b["close"]

        if not self.in_attack:
            if self.prev_close < self.key and bar_high >= self.key:
                self.in_attack = True
                self.attack_bars = [b]
                # Production closes immediately if close falls back below key.
                if bar_close < self.key:
                    self.completed.append(BUILD_ATTACK(copy.deepcopy(self.attack_bars), self.key))
                    self.in_attack = False
                    self.attack_bars = []
        else:
            self.attack_bars.append(b)
            if bar_close < self.key:
                self.completed.append(BUILD_ATTACK(copy.deepcopy(self.attack_bars), self.key))
                self.in_attack = False
                self.attack_bars = []

        self.prev_close = bar_close
        self.last_minute = t

    def snapshot_attacks(self) -> list[dict]:
        out = copy.deepcopy(self.completed)
        # OLD find_attacks closes an open attack at the current last row via is_last.
        if self.in_attack and self.attack_bars:
            out.append(BUILD_ATTACK(copy.deepcopy(self.attack_bars), self.key))
        return out

@dataclass
class FastP1State:
    initialized: bool = False
    key: float | None = None
    key_time: str | None = None
    prev_scan_close: float | None = None
    a1_time: str | None = None
    a1_abs: float | None = None

    terminal_broken: bool = False
    reason: str | None = None

    # episode state
    next_ep: float | None = None
    ep_prev_close: float | None = None
    ep_prev_hi: float | None = None
    ep_prev_g: bool = False
    gs: int = 0
    fe: int = 0
    broke_after_a1: bool = False
    running_hi: float | None = None

    # P1 / frontier
    p1_abs: float | None = None
    p1_time: str | None = None
    post_entry_time: str | None = None
    post_entry_open: float | None = None
    post_runmax: float | None = None
    frontier_time: str | None = None

    last_minute: str | None = None

    def initialize_after_0910(self, d: pd.DataFrame) -> None:
        early = d[d["time_str"] <= "09:10:00"]
        if early.empty:
            return
        self.key = float(pd.to_numeric(early["high"], errors="coerce").max())
        kr = early[np.isclose(pd.to_numeric(early["high"], errors="coerce"),
                              self.key, rtol=0, atol=1e-9)]
        if kr.empty:
            return
        self.key_time = str(kr.iloc[0]["time_str"])
        prev = d[d["time_str"] <= self.key_time]
        if prev.empty:
            return
        self.prev_scan_close = float(prev.iloc[-1]["close"])
        self.initialized = True
        self.last_minute = "09:10:00"

        # Production p1_find_a1 scans rows after key_time, including rows that may
        # still be <=09:10 if key was created earlier. Reproduce that once here.
        obs = d[(d["time_str"] > self.key_time) & (d["time_str"] <= "09:10:00")]
        for _, r in obs.iterrows():
            if self.a1_time is None:
                if self.prev_scan_close < self.key - 1e-9 and float(r["high"]) >= self.key - 1e-9:
                    self._set_a1(r)
            self.prev_scan_close = float(r["close"])

    def _set_a1(self, r) -> None:
        self.a1_time = str(r["time_str"])
        self.a1_abs = float(r["minute_abs"])
        c = float(r["close"])
        h = float(r["high"])
        if c < self.key - 1e-9:
            self.terminal_broken = True
            self.reason = "A1_SAME_MINUTE_CLOSE_BELOW_KEY"
            self.gs = 0
            self.fe = 0
            return
        self.ep_prev_close = c
        self.ep_prev_hi = h
        self.ep_prev_g = False
        self.running_hi = h
        self.next_ep = math.floor(self.a1_abs / 5.0) * 5.0 + 5.0

    def step(self, r) -> None:
        if not self.initialized:
            stop("FAST P1 stepped before initialization")
        t = str(r["time_str"])
        ma = float(r["minute_abs"])
        c = float(r["close"])
        h = float(r["high"])

        if self.last_minute is not None and t <= self.last_minute:
            stop(f"FAST P1 non-increasing input: {t} <= {self.last_minute}")

        if self.a1_time is None:
            if self.prev_scan_close < self.key - 1e-9 and h >= self.key - 1e-9:
                self._set_a1(r)
            self.prev_scan_close = c
            self.last_minute = t
            return

        self.prev_scan_close = c

        if self.terminal_broken:
            self.last_minute = t
            return

        if self.p1_abs is None:
            if ma > self.a1_abs + 1e-12 and c < self.key - 1e-9:
                self.broke_after_a1 = True
            self.running_hi = max(float(self.running_hi), h)

            if self.next_ep is not None and ma >= self.next_ep - 1e-12:
                # Canonical is 1m ordered; endpoint row is current when ma==next_ep.
                # If there were missing endpoint bars, OLD uses last row <= endpoint.
                # This auditor's canonical coverage will expose any mismatch.
                cur = c
                hi = float(self.running_hi)
                g = cur > float(self.ep_prev_close) + 1e-9
                f = hi > float(self.ep_prev_hi) + 1e-9
                start = bool(g and not self.ep_prev_g)
                if start:
                    self.gs += 1
                if f:
                    self.fe += 1
                if self.gs >= 2 and self.fe >= 1:
                    if self.broke_after_a1:
                        self.terminal_broken = True
                    else:
                        self.p1_abs = float(self.next_ep)
                        self.p1_time = f"{int(self.p1_abs//60):02d}:{int(self.p1_abs%60):02d}:00"
                        # OLD full-replay semantics: P1 belongs to the episode
                        # endpoint, but if that endpoint is discovered while
                        # processing a later actual row, this same row is the
                        # first row strictly after P1.
                        if ma > self.p1_abs + 1e-12 and self.post_entry_time is None:
                            self.post_entry_time = t
                            self.post_entry_open = float(r["open"])
                            self.post_runmax = c
                self.ep_prev_close = cur
                self.ep_prev_hi = hi
                self.ep_prev_g = g
                self.next_ep += 5.0

        else:
            # Production post-P1 baseline is the first row strictly after P1.
            if ma > self.p1_abs + 1e-12:
                if self.post_entry_time is None:
                    self.post_entry_time = t
                    self.post_entry_open = float(r["open"])
                    self.post_runmax = c
                elif self.frontier_time is None:
                    if c > float(self.post_runmax) + 1e-12:
                        self.frontier_time = t
                    self.post_runmax = max(float(self.post_runmax), c)

        self.last_minute = t

    def result(self) -> dict:
        if self.a1_time is None:
            return {"status": "TRACKING", "a1_time": None,
                    "p1_time": None, "frontier_time": None}
        if self.terminal_broken:
            z = {"status": "NO_P1_A1_BROKEN",
                 "a1_time": self.a1_time, "p1_time": None,
                 "frontier_time": None,
                 "g_episode_starts": self.gs, "frontier_events": self.fe}
            if self.reason:
                z["reason"] = self.reason
            return z
        if self.p1_time is None:
            return {"status": "TRACKING", "a1_time": self.a1_time,
                    "p1_time": None, "frontier_time": None,
                    "g_episode_starts": self.gs, "frontier_events": self.fe}
        z = {
            "status": "P1_FRONTIER" if self.frontier_time else "P1",
            "a1_time": self.a1_time,
            "p1_time": self.p1_time,
            "frontier_time": self.frontier_time,
            "g_episode_starts": self.gs,
            "frontier_events": self.fe,
        }
        if self.post_entry_time is not None:
            z["post_p1_entry_time"] = self.post_entry_time
            z["post_p1_entry_open"] = self.post_entry_open
        return z

class EarlyState:
    def __init__(self,a2_abs):
        self.a2_abs=float(a2_abs)
        self.prev_D=0.0
        self.prev_MFE=0.0
        self.direction_seen=False
        self.generation_seen=False
        self.frontier_seen=False
        self.recurrence_seen=False
        self.seen_gen=False
        self.pause_since_gen=False
        self.next_ep=self.a2_abs+float(earlymod.SEG)
        self.terminal=None
        self.last_endpoint=None
    def advance(self,d,through_abs):
        while self.terminal is None and self.next_ep<=through_abs+EPS:
            st=earlymod.state_at(d,self.a2_abs,self.next_ep)
            if st is None: break
            _,_,D,MFE=st
            raw_gen=float(D)-float(self.prev_D)>EPS
            raw_frontier=float(MFE)>float(self.prev_MFE)+EPS
            self.direction_seen=self.direction_seen or float(D)>EPS
            self.generation_seen=self.generation_seen or raw_gen
            self.frontier_seen=self.frontier_seen or raw_frontier
            recurrence_event=False
            if raw_gen:
                if self.seen_gen and self.pause_since_gen:
                    recurrence_event=True
                self.seen_gen=True; self.pause_since_gen=False
            elif self.seen_gen:
                self.pause_since_gen=True
            self.recurrence_seen=self.recurrence_seen or recurrence_event
            self.prev_D=float(D); self.prev_MFE=float(MFE)
            self.last_endpoint=float(self.next_ep)
            if self.direction_seen and self.generation_seen and self.frontier_seen and self.recurrence_seen:
                self.terminal=float(self.next_ep)
                break
            self.next_ep += float(earlymod.SEG)
        return self
    def result(self):
        if self.terminal is None:
            return {"status":"NO_EARLY","recognition_time":None}
        h=int(self.terminal//60); mi=int(self.terminal%60)
        return {"status":"EARLY","recognition_time":f"{h:02d}:{mi:02d}:00"}
