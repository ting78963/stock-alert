# -*- coding: utf-8 -*-
"""
FUGLE B LIVE RUNNER v2+P1 | ABC unchanged + independent P1
Production one-stock runner prepared for actual market-hours REST -> WS validation.

Uses existing audited local files:
- fugle_b_engine_v2.py
- fugle_b_data_adapter_v1.py
- original Attack / Frozen Early implementations referenced by b_engine_v2

Adds vs v1:
1) timezone-aware Asia/Taipei clock (no utcnow deprecation)
2) persistent canonical minute JSONL
3) completed-minute gate: evaluate minute M only after Taipei clock >= M+1 minute
4) startup causal cutoff = min(discovered_at, current completed minute) for TODAY
5) reconnect: REST reconcile -> canonical audit -> replay -> WS resume
6) explicit REST/WS continuity counters and live-test summary
7) persistent stock/date signal dedupe
8) never backdates execution; execution filled only after a later observed completed minute

LINE notifier integration: default DRY RUN; --line-send enables real push immediately when A/B/C/P1 recognition is confirmed. Execution OPEN is logged later for research only. NO scanner A. No source/data writes.
Output only:
Desktop/?啣?鞈?憭?_production_output/b_live_runner_v2/

Estimated runtime:
startup ~1-5 sec; then requested --minutes.
Main bottleneck: Fugle network / live WS event availability.
"""
from __future__ import annotations
import argparse, json, os, runpy, time, threading, re, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd

HOME=Path.home(); BASE=Path(__file__).resolve().parent
CORE=BASE/"fugle_b_engine_v2_p1.py"; ADAPTER=BASE/"fugle_b_data_adapter_v1.py"; NOTIFIER=BASE/"line_signal_notifier_v3.py"
STATE_ROOT=Path(os.environ.get("PRODUCTION_STATE_DIR",str(BASE/"_production_output")))
OUT=STATE_ROOT/"b_live_runner_v2_p1"
TPE=ZoneInfo("Asia/Taipei"); EPS=1e-12

def banner(s): print("\n"+"="*154+"\n"+s+"\n"+"="*154)
def stop(s):
    banner("AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL")
    print(s); raise SystemExit(2)
def nt(x):
    s=str(x).strip()
    if len(s)==5:s+=":00"
    return pd.to_datetime(s).strftime("%H:%M:%S")
def ma(s):
    h,m,*q=nt(s).split(":"); return int(h)*60+int(m)+(int(q[0]) if q else 0)/60
def now_tpe(): return datetime.now(TPE)
def completed_cutoff(now=None):
    """Latest minute label guaranteed complete by wall clock: current minute - 1."""
    z=(now or now_tpe()).replace(second=0,microsecond=0)-timedelta(minutes=1)
    return z.strftime("%H:%M:00")

class Runner:
    def __init__(self,sid,date,disc,watch,line_send=False,stock_name=""):
        self.sid=str(sid).zfill(4); self.date=date; self.disc=nt(disc); self.watch=float(watch); self.line_send=bool(line_send)
        self.stock_name=str(stock_name or "").strip()
        # PHASE 1 causal completed-minute dedupe: RAM-only scheduling state.
        self._dirty_minutes=set()
        self._last_completed_through=None
        self.rows={}; self.last_state=None; self.last_p1_status=None; self.lock=threading.Lock()
        self.ws_messages=self.ws_candles=self.ws_new=self.ws_changed=0
        self.reconnects=self.server_errors=0; self.rest_reconciles=0
        self.first_ws_candle=None; self.last_ws_candle=None

        if not CORE.exists():stop(f"Missing {CORE}")
        if not ADAPTER.exists():stop(f"Missing {ADAPTER}")
        try:self.m=runpy.run_path(str(CORE),run_name="__live_v2_p1_core__")
        except BaseException as e:stop(f"Cannot load B Engine v3: {e!r}")
        A=self.m["ATTACK"]; E=self.m["EARLY"]
        if self.m["sha"](A)!=self.m["ATTACK_SHA"]:stop("Attack code SHA mismatch.")
        try:
            at=runpy.run_path(str(A),run_name="__live_v3_attack__")
            er=runpy.run_path(str(E),run_name="__live_v3_early__")
            at["load_attack_engine"].__globals__["PROJECT"] = BASE
            self.fa,self.cc,self.fe=at["load_attack_engine"]()
            self.bars_df=er["bars_df"]; self.reconstruct=er["reconstruct_a2"]; self.replay=er["replay_early"]
        except BaseException as e:stop(f"Frozen implementation load failed: {e!r}")
        self.key,self.key_source=self.m["find_key"]()
        self.pdate,self.pc,self.pv=self.m["fetch_prev"](self.key,self.sid,self.date)
        if self.pc<=0 or self.pv<=0:stop("Invalid prior context.")

        self.dir=OUT/self.date/self.sid; self.dir.mkdir(parents=True,exist_ok=True)
        self.canon=self.dir/"canonical_minutes.jsonl"
        self.sig=self.dir/"signal_event.json"
        self.p1sig=self.dir/"p1_signal_event.json"
        self.state=self.dir/"runner_state.json"
        self.signal_emitted=self.sig.exists()
        self.p1_signal_emitted=self.p1sig.exists()
        # Presentation metadata recovery only: A already knows the TW stock name.
        # Backfill it into persisted events without changing recognition identity.
        if self.stock_name:
            for ep in (self.sig,self.p1sig):
                if ep.exists():
                    try:
                        eo=json.loads(ep.read_text(encoding="utf-8"))
                        if not str(eo.get("stock_name") or "").strip():
                            eo["stock_name"]=self.stock_name
                            tmp=ep.with_suffix(ep.suffix+".tmp")
                            tmp.write_text(json.dumps(eo,ensure_ascii=False,indent=2),encoding="utf-8")
                            tmp.replace(ep)
                    except Exception as ex:
                        stop(f"Cannot backfill stock_name into {ep.name}: {ex!r}")
        self.load_canonical()

    def load_canonical(self):
        if not self.canon.exists():return
        try:
            for line in self.canon.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r=json.loads(line); self.rows[nt(r["minute"])]=r
        except Exception as e:stop(f"Persistent canonical store unreadable: {e!r}")
        self.audit_canonical("load")

    def save_canonical(self):
        tmp=self.canon.with_suffix(".jsonl.tmp")
        with tmp.open("w",encoding="utf-8") as f:
            for k in sorted(self.rows):
                f.write(json.dumps(self.rows[k],ensure_ascii=False)+"\n")
        tmp.replace(self.canon)

    def append_canonical(self,minutes):
        with self.canon.open("a",encoding="utf-8") as f:
            for k in sorted(minutes):
                f.write(json.dumps(self.rows[k],ensure_ascii=False)+"\n")

    def audit_canonical(self,label):
        ks=sorted(self.rows)
        if len(ks)!=len(set(ks)):stop(f"{label}: duplicate canonical minute")
        if any(ks[i]>=ks[i+1] for i in range(len(ks)-1)):stop(f"{label}: non-increasing canonical minute")
        for k in ks:
            r=self.rows[k]
            vals=[float(r[x]) for x in ("open","high","low","close","volume")]
            o,h,l,c,v=vals
            if min(o,h,l,c)<=0 or v<0 or h+EPS<max(o,c,l) or l-EPS>min(o,c,h):
                stop(f"{label}: bad OHLCV at {k}")
        return True

    def merge(self,rows,source):
        add=chg=dup=0
        prior_max=max(self.rows) if self.rows else None
        added_times=[]
        for r in rows:
            t=nt(r["minute"])
            z={"date":self.date,"stock_id":self.sid,"minute":t,
               "open":float(r["open"]),"high":float(r["high"]),"low":float(r["low"]),
               "close":float(r["close"]),"volume":float(r["volume"])}
            old=self.rows.get(t)
            if old is None:
                self.rows[t]=z;add+=1;added_times.append(t);self._dirty_minutes.add(t)
            elif all(abs(float(old[k])-float(z[k]))<=EPS for k in ("open","high","low","close","volume")):
                dup+=1
            else:
                self.rows[t]=z;chg+=1;self._dirty_minutes.add(t)
        if source=="ws":
            self.ws_new+=add; self.ws_changed+=chg
        self.audit_canonical("merge-"+source)
        if chg or any(prior_max is not None and t<=prior_max for t in added_times):
            self.save_canonical()
        elif added_times:
            self.append_canonical(added_times)
        return add,chg,dup

    def df(self,through=None):
        vals=[self.rows[k] for k in sorted(self.rows)]
        if through:vals=[r for r in vals if nt(r["minute"])<=nt(through)]
        return self.bars_df(vals,self.date,self.sid) if vals else pd.DataFrame()

    def evaluate(self,through,origin):
        d=self.df(through)
        if d.empty:return
        a=self.reconstruct(d,self.pc,self.pv,self.fa,self.cc,self.fe)
        typ="NO_BUY"; early=None; st="TRACKING"
        if int(a.get("attack_count",0))>=2 and bool(a.get("a2_upward")):
            typ=self.m["abc"](float(a.get("a2_vr",np.nan)),float(a.get("early_high_pct",np.nan)))
            if typ!="NO_BUY":
                early=self.replay(d,a["a2_end"])
                if early.get("early_status")=="EARLY":st="SIGNAL"
        if st!=self.last_state:
            print(f"[STATE] through={nt(through)} | {self.last_state or 'INIT'} -> {st} | ABC={typ}")
            self.last_state=st
        if st=="SIGNAL":
            recog=nt(early["early_time"])
            live=self.disc if ma(self.disc)>ma(recog) else recog
            # Recovery semantics: completed replay may prove that recognition
            # happened before discovery/restart. Emit immediately once the
            # recognition minute is contained in causal completed data; do not
            # wait for a new post-recovery minute merely to deliver the alert.
            if ma(through)+EPS>=ma(recog) and not self.signal_emitted:
                e={"schema":"b_signal_event_v1","date":self.date,"stock_id":self.sid,
                   "signal_class":typ,"discovered_at":self.disc,"recognition_time":recog,
                    "stock_name":self.stock_name,
                   "live_known_time":live,"signal_emitted_at_feed_through":nt(through),
                   "a2_end":a.get("a2_end"),"a2_vr":float(a["a2_vr"]),
                   "early_high_pct":float(a["early_high_pct"]),
                   "frozen_early_price":float(early["early_price"]),
                   "late_discovery":bool(ma(self.disc)>ma(recog)),
                   "execution_policy":"first observed COMPLETED minute OPEN strictly after live_known_time",
                   "execution_time":None,"execution_open":None,
                   "source":"Fugle","origin":origin,"dry_run":True,"line_sent":False}
                self.sig.write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding="utf-8")
                self.signal_emitted=True
                banner("NEW SIGNAL EVENT | persistent stock/date dedupe")
                print(json.dumps(e,ensure_ascii=False,indent=2))
                self._notify_if_recognized(self.sig,"ABC")
        self.evaluate_p1(d,through,origin)
        self.fill_execution(through,d)
        self.persist(through,st,typ,origin)

    def evaluate_p1(self,d,through,origin):
        p=self.m["p1_replay"](d)
        ps=p.get("status")
        if ps!=self.last_p1_status:
            print(f"[P1 STATE] through={nt(through)} | {self.last_p1_status or 'INIT'} -> {ps} | A1={p.get('a1_time')} | P1={p.get('p1_time')} | Frontier={p.get('frontier_time')} | reason={p.get('reason')}")
            self.last_p1_status=ps
        if ps!="P1_FRONTIER":return
        recog=nt(p["frontier_time"])
        live=self.disc if ma(self.disc)>ma(recog) else recog
        # Same recovery rule as ABC: an already-established P1/Frontier is
        # delivered immediately when completed replay proves it.
        if ma(through)+EPS<ma(recog) or self.p1_signal_emitted:return
        e={"schema":"b_signal_event_v2","date":self.date,"stock_id":self.sid,
           "signal_class":"P1","discovered_at":self.disc,
            "stock_name":self.stock_name,
           "a1_time":p.get("a1_time"),"p1_time":p.get("p1_time"),
           "post_p1_entry_time":p.get("post_p1_entry_time"),
           "post_p1_entry_open":p.get("post_p1_entry_open"),
           "recognition_time":recog,"live_known_time":live,
           "signal_emitted_at_feed_through":nt(through),
           "late_discovery":bool(ma(self.disc)>ma(recog)),
           "execution_policy":"first observed COMPLETED minute OPEN strictly after live_known_time",
           "execution_time":None,"execution_open":None,
           "source":"Fugle","origin":origin,"dry_run":True,"line_sent":False}
        self.p1sig.write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding="utf-8")
        self.p1_signal_emitted=True
        banner("NEW P1 SIGNAL EVENT | independent persistent stock/date dedupe")
        print(json.dumps(e,ensure_ascii=False,indent=2))
        self._notify_if_recognized(self.p1sig,"P1")

    def _fill_one_execution(self,path,label,through,d):
        if not path.exists():return
        e=json.loads(path.read_text(encoding="utf-8"))
        if e.get("execution_time"):return
        z=d[d.minute_abs>ma(e["live_known_time"])+EPS].sort_values("minute_abs",kind="stable")
        if z.empty:return
        r=z.iloc[0]; e["execution_time"]=str(r.time_str); e["execution_open"]=float(r.open)
        path.write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"[{label} EXECUTION OBSERVED] {r.time_str} OPEN={float(r.open)}")

    def _notify_if_recognized(self,path,label):
        if not path.exists():return
        e=json.loads(path.read_text(encoding="utf-8"))
        if not NOTIFIER.is_file():
            print(f"[{label} LINE SKIPPED] notifier missing: {NOTIFIER}")
            return
        # Normal delivery uses line_sent as persistent dedupe. Events already
        # delivered by legacy v2 are resent exactly once as approved Flex v3.
        migration=(e.get("line_sent") is True and e.get("flex_v3_sent") is not True)
        if e.get("line_sent") is True and not migration:return
        cmd=[sys.executable,str(NOTIFIER),str(path)]
        if self.line_send:cmd.append("--send")
        if migration:cmd.append("--flex-migration")
        mode="REAL SEND" if self.line_send else "DRY RUN"
        action="FLEX V3 MIGRATION RESEND" if migration else f"LINE {mode}"
        print(f"[{label} {action}] recognition confirmed -> notifier v3")
        cp=subprocess.run(cmd,check=False)
        if cp.returncode!=0:
            print(f"[{label} LINE FAILED] notifier exit={cp.returncode}; recognition/execution unchanged.")

    def fill_execution(self,through,d):
        # Research ledger only: after recognition, persist the first observed
        # completed minute OPEN strictly after live_known_time.
        self._fill_one_execution(self.sig,"ABC",through,d)
        self._fill_one_execution(self.p1sig,"P1",through,d)

    def persist(self,through,st,typ,origin):
        x={"date":self.date,"stock_id":self.sid,"through":nt(through),"state":st,"abc":typ,
           "origin":origin,"signal_emitted":self.signal_emitted,"p1_signal_emitted":self.p1_signal_emitted,
           "canonical_minutes":len(self.rows),"rest_reconciles":self.rest_reconciles,
           "ws_messages":self.ws_messages,"ws_candles":self.ws_candles,
           "ws_new":self.ws_new,"ws_changed":self.ws_changed,"reconnects":self.reconnects,
           "updated_at_taipei":now_tpe().isoformat(timespec="seconds")}
        self.state.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")

    def rest_reconcile(self,label):
        self.rest_reconciles+=1
        rows=self.m["adapt"](self.m["fetch"](self.key,self.sid,self.date),self.date,self.sid)
        today=now_tpe().strftime("%Y-%m-%d")
        if label=="startup":
            if self.date==today:
                # Causal startup boundary: never consume the currently-forming
                # minute, and never replay beyond the actual discovery timestamp.
                completed=completed_cutoff()
                cut=self.disc if ma(self.disc)<=ma(completed) else completed
            else:
                cut=self.disc
            rows=[r for r in rows if nt(r["minute"])<=cut]
        elif self.date==today:
            # Reconnect may use only guaranteed completed bars.
            cut=completed_cutoff()
            rows=[r for r in rows if nt(r["minute"])<=cut]
        a,c,d=self.merge(rows,"rest")
        if not self.rows:stop(f"REST {label}: no canonical rows")
        through=max(self.rows)
        print(f"[REST {label}] input={len(rows)} add={a} changed={c} exact_dup={d} canonical={len(self.rows)} through={through}")
        if label=="startup":
            # Crash/restart recovery: event identity is already persistent.
            # Retry delivery only when LINE has not previously succeeded.
            self._notify_if_recognized(self.sig,"ABC")
            self._notify_if_recognized(self.p1sig,"P1")
        self.evaluate(through,label)
        self._mark_evaluated_through(through)

    def ws_url(self):
        txt=ADAPTER.read_text(encoding="utf-8",errors="ignore")
        u=re.findall(r'wss://[^"\']+',txt)
        if not u:stop("Cannot recover proven Fugle WS URL from adapter.")
        return u[0]

    def parse_candle(self,msg):
        try:o=json.loads(msg)
        except:return None
        self.ws_messages+=1
        stack=[o]
        while stack:
            x=stack.pop()
            if isinstance(x,list):stack.extend(x);continue
            if not isinstance(x,dict):continue
            for k in ("data","candle","candles"):
                if k in x:stack.append(x[k])
            sym=str(x.get("symbol") or x.get("code") or "")
            if sym and sym!=self.sid:continue
            if not all(k in x for k in ("open","high","low","close","volume")):continue
            raw=x.get("date") or x.get("time") or x.get("timestamp")
            if raw is None:continue
            try:
                if isinstance(raw,(int,float)):
                    unit="ms" if raw>10**11 else "s"
                    dt=pd.to_datetime(raw,unit=unit,utc=True).tz_convert("Asia/Taipei")
                else:
                    dt=pd.to_datetime(raw)
                    if dt.tzinfo is not None:dt=dt.tz_convert("Asia/Taipei")
                ds=dt.strftime("%Y-%m-%d"); ts=dt.strftime("%H:%M:00")
            except:continue
            if ds!=self.date:continue
            self.ws_candles+=1
            return {"date":ds,"stock_id":self.sid,"minute":ts,
                    "open":x["open"],"high":x["high"],"low":x["low"],"close":x["close"],"volume":x["volume"]}
        return None

    def _mark_evaluated_through(self,through):
        through=nt(through)
        self._last_completed_through=through
        # Future/forming dirty minutes remain dirty until causally completed.
        self._dirty_minutes={k for k in self._dirty_minutes if k>through}

    def evaluate_completed(self,origin):
        cut=completed_cutoff()
        eligible=[k for k in self.rows if k<=cut]
        if not eligible:return
        through=max(eligible)
        causal_dirty=any(k<=through for k in self._dirty_minutes)
        if through==self._last_completed_through and not causal_dirty:
            return
        # Only successful evaluation may advance/clean scheduler state.
        self.evaluate(through,origin)
        self._mark_evaluated_through(through)

    def run_ws(self):
        try:import websocket
        except ImportError:stop("Install websocket-client first.")
        end=time.monotonic()+self.watch*60; backoff=2
        while time.monotonic()<end:
            def on_open(ws):
                ws.send(json.dumps({"event":"auth","data":{"apikey":self.key}}))
            def on_message(ws,msg):
                try:
                    o=json.loads(msg)
                    ev=str(o.get("event","")) if isinstance(o,dict) else ""
                    if ev=="authenticated":
                        ws.send(json.dumps({"event":"subscribe","data":{"channel":"candles","symbol":self.sid}}))
                        print(f"[WS] authenticated; subscribed candles/{self.sid}");return
                    if ev in ("error","server_error"):
                        self.server_errors+=1;print("[WS SERVER ERROR]",str(o)[:300]);return
                except:pass
                r=self.parse_candle(msg)
                if r is None:return
                with self.lock:
                    if self.first_ws_candle is None:self.first_ws_candle=r["minute"]
                    self.last_ws_candle=r["minute"]
                    a,c,d=self.merge([r],"ws")
                    print(f"[WS CANDLE] {r['minute']} | add={a} changed={c} dup={d}")
                    self.evaluate_completed("websocket_completed_minute")
            def on_error(ws,e):print("[WS ERROR]",repr(e))
            def on_close(ws,*args):print("[WS] closed")
            app=websocket.WebSocketApp(self.ws_url(),on_open=on_open,on_message=on_message,on_error=on_error,on_close=on_close)
            th=threading.Thread(target=app.run_forever,daemon=True);th.start()
            while th.is_alive() and time.monotonic()<end:
                # A minute can become complete without another WS update, so clock-tick evaluation matters.
                with self.lock:self.evaluate_completed("clock_completed_minute")
                time.sleep(1)
            try:app.close()
            except:pass
            if time.monotonic()>=end:break
            self.reconnects+=1
            print(f"[RECONNECT] #{self.reconnects}: REST reconcile before resubscribe")
            self.rest_reconcile("reconnect")
            time.sleep(min(backoff,max(0,end-time.monotonic())));backoff=min(backoff*2,30)

    def summary(self):
        banner("LIVE TEST SUMMARY")
        print(f"canonical_minutes={len(self.rows)} | ABC_signal={self.signal_emitted} | P1_signal={self.p1_signal_emitted}")
        print(f"REST reconciles={self.rest_reconciles}")
        print(f"WS messages={self.ws_messages} | candle payloads={self.ws_candles}")
        print(f"WS new={self.ws_new} | changed/reconciled={self.ws_changed}")
        print(f"first_ws_candle={self.first_ws_candle} | last_ws_candle={self.last_ws_candle}")
        print(f"reconnects={self.reconnects} | server_errors={self.server_errors}")
        if self.watch>0 and self.date==now_tpe().strftime("%Y-%m-%d"):
            if self.ws_candles==0:
                print("LIVE REST->WS TRANSITION: NOT YET OBSERVED (no candle payload received)")
            else:
                print("LIVE REST->WS TRANSPORT: OBSERVED")
                print("Decision-semantic validation still depends on whether a qualifying A/B/C state occurs during this watch.")
        else:print("LIVE REST->WS TRANSITION: NOT TESTED in this run")
        print("LINE mode:", "REAL SEND" if self.line_send else "DRY RUN")

    def run(self):
        banner(f"FUGLE B LIVE RUNNER v2+P1 | ABC unchanged + independent P1 | {self.sid} / {self.date} | discovered_at={self.disc}")
        print(f"timezone=Asia/Taipei | LINE={'REAL SEND' if self.line_send else 'DRY RUN'} | persistent canonical store + signal dedupe")
        print(f"prior={self.pdate} close={self.pc} volume={self.pv:g}")
        print(f"key=<REDACTED> ({self.key_source})")
        if self.signal_emitted:
            print("[DEDUPE] prior ABC signal exists; duplicate ABC emission disabled.")
            self._notify_if_recognized(self.sig,"ABC")
        if self.p1_signal_emitted:
            print("[DEDUPE] prior P1 signal exists; duplicate P1 emission disabled.")
            self._notify_if_recognized(self.p1sig,"P1")
        self.rest_reconcile("startup")
        today=now_tpe().strftime("%Y-%m-%d")
        if self.date!=today:
            print(f"[WS SKIPPED] target={self.date}, Taipei today={today}")
        elif self.watch>0:self.run_ws()
        self.summary()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--date",required=True)
    ap.add_argument("--discovered-at",required=True)
    ap.add_argument("--minutes",type=float,default=30)
    ap.add_argument("--line-send",action="store_true",help="Actually send LINE immediately when A/B/C/P1 recognition is confirmed.")
    a=ap.parse_args();Runner(a.symbol,a.date,a.discovered_at,a.minutes,a.line_send).run()
if __name__=="__main__":main()