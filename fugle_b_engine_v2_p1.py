# -*- coding: utf-8 -*-
"""
FUGLE B ENGINE v2+P1 | ABC unchanged + independent P1

Purpose
-------
B receives one discovered stock and a live-known timestamp, backfills Fugle 1m
from market open, replays the exact existing Attack + Frozen Early logic, assigns
A/B/C, and emits a machine-readable Signal Event only when causally knowable.

NO LINE SEND YET.  NO scanner A.  NO source/data writes.
Output only: Desktop/?啣?鞈?憭?_production_output/b_engine_v2/

Important live semantics
------------------------
recognition_time = when Frozen Early existed in the reconstructed market path.
live_known_time  = when production B could actually know it (>= discovery time,
                   and >= recognition time).
execution_time   = first OBSERVED minute strictly after live_known_time.
Therefore late discovery NEVER backdates a buy to the historical next-minute open.

A = VR<0.5  & EH 3-<5
B = VR<0.5  & EH 5-<6
C = VR>=0.5 & EH 5-<6

Estimated runtime: ~1-5 sec.
Main bottleneck: Fugle historical REST requests.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, runpy, sys, time
import urllib.error, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd

HOME=Path.home(); BASE=HOME/"Desktop"/"新增資料夾"
OUT=BASE/"_production_output"/"b_engine_v2_p1"
FUGLE="https://api.fugle.tw/marketdata/v1.0/stock"; TIMEOUT=20; EPS=1e-12
ATTACK=BASE/"run_strong_x_frozen_trend_live_auditor_v4.py"
EARLY=BASE/"audit_strong_4day_frozen_early_abc_buy_2026_v1.py"
ATTACK_SHA="e3be0e0f38f6d58f58595bdf50987479fda230ffa4c995d43cf89efc185dd323"

def banner(s): print("\n"+"="*142+"\n"+s+"\n"+"="*142)
def stop(s):
    banner("AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL")
    print(s); raise SystemExit(2)
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def nt(x):
    s=str(x).strip()
    if len(s)==5:s+=":00"
    try:return pd.to_datetime(s).strftime("%H:%M:%S")
    except:return s[:8]
def mins(s):
    h,m,*z=nt(s).split(":"); return int(h)*60+int(m)+(int(z[0]) if z else 0)/60
def find_key():
    v=os.getenv("FUGLE_API_KEY","").strip()
    if v:return v,"FUGLE_API_KEY environment variable"
    names=["Fugle_live_KBar_test_ready.py","Fugle_historical_5day_volume_test_ready.py","Fugle_snapshot_strong_test_ready.py"]
    fs=[]
    for root in [HOME/"Desktop",HOME/"Downloads",HOME/"Documents"]:
        if not root.exists():continue
        for n in names:
            try:fs+=list(root.rglob(n))
            except:pass
        try:fs+=list(root.rglob("Fugle*.py"))
        except:pass
    pats=[r'(?m)^\s*API_KEY\s*=\s*["\']([^"\']{16,})["\']',r'(?m)^\s*FUGLE_API_KEY\s*=\s*["\']([^"\']{16,})["\']']
    seen=set()
    for p in fs:
        try:
            rp=str(p.resolve())
            if rp in seen or p.resolve()==Path(__file__).resolve():continue
            seen.add(rp); t=p.read_text(encoding="utf-8",errors="ignore")
        except:continue
        for q in pats:
            m=re.search(q,t)
            if m:return m.group(1).strip(),str(p)
    stop("Fugle API key not found.")
def fetch(key,sid,date):
    q=urllib.parse.urlencode({"timeframe":"1","from":date,"to":date,"fields":"open,high,low,close,volume,average","sort":"asc"})
    u=f"{FUGLE}/historical/candles/{sid}?{q}"
    req=urllib.request.Request(u,headers={"X-API-KEY":key,"Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=TIMEOUT) as r:o=json.loads(r.read().decode())
    except urllib.error.HTTPError as e:stop(f"Fugle HTTP {e.code} | {date} | "+e.read().decode(errors="replace")[:300])
    if str(o.get("symbol"))!=sid or str(o.get("timeframe"))!="1" or not o.get("data"):stop(f"Fugle identity/coverage failed: {date}")
    return o
def adapt(o,date,sid):
    a=[]; seen=set()
    for b in o["data"]:
        dt=pd.to_datetime(b["date"]); ds=dt.strftime("%Y-%m-%d"); ts=dt.strftime("%H:%M:%S")
        if ds!=date:stop(f"Date leakage {ds} != {date}")
        if ts in seen:stop(f"Duplicate minute {date} {ts}")
        seen.add(ts)
        z={k:b.get(k) for k in ("open","high","low","close","volume")}
        if any(v is None for v in z.values()):stop(f"Missing OHLCV {date} {ts}")
        a.append({"date":date,"stock_id":sid,"minute":ts,**z})
    return a
def abc(vr,eh):
    if not np.isfinite(vr) or not np.isfinite(eh):return "NO_BUY"
    if vr<.5 and 3<=eh<5:return "A"
    if vr<.5 and 5<=eh<6:return "B"
    if vr>=.5 and 5<=eh<6:return "C"
    return "NO_BUY"

def p1_find_a1(d):
    if d is None or d.empty:return None
    x=d.copy().sort_values("minute_abs",kind="stable")
    early=x[x["time_str"]<="09:10:00"]
    if early.empty:return None
    key=float(pd.to_numeric(early["high"],errors="coerce").max())
    kr=early[np.isclose(pd.to_numeric(early["high"],errors="coerce"),key,rtol=0,atol=1e-9)]
    if kr.empty:return None
    kt=str(kr.iloc[0]["time_str"])
    prev=x[x["time_str"]<=kt]; obs=x[x["time_str"]>kt]
    if prev.empty or obs.empty:return {"key_price":key,"key_time":kt,"a1_time":None}
    pc=float(prev.iloc[-1]["close"])
    for _,r in obs.iterrows():
        if pc<key-1e-9 and float(r["high"])>=key-1e-9:
            return {"key_price":key,"key_time":kt,"a1_time":str(r["time_str"])}
        pc=float(r["close"])
    return {"key_price":key,"key_time":kt,"a1_time":None}

def p1_replay(d):
    a1=p1_find_a1(d)
    if not a1 or not a1.get("a1_time"):
        return {"status":"TRACKING","a1_time":None,"p1_time":None,"frontier_time":None}
    x=d.copy().sort_values("minute_abs",kind="stable")
    key=float(a1["key_price"]); a1t=nt(a1["a1_time"]); am=mins(a1t)
    ar=x[np.isclose(x["minute_abs"].astype(float),am,rtol=0,atol=1e-12)]
    if ar.empty:return {"status":"ERROR","reason":"NO_EXACT_A1_BAR"}
    ar=ar.iloc[-1]; prev_close=float(ar["close"]); prev_hi=float(ar["high"])
    # Frozen P1 semantics: a Close<Key on the A1 bar itself is the first natural
    # Break immediately. Such an A1 can never remain intact through Body/P1.
    if prev_close < key-1e-9:
        return {"status":"NO_P1_A1_BROKEN","reason":"A1_SAME_MINUTE_CLOSE_BELOW_KEY",
                "a1_time":a1t,"p1_time":None,"frontier_time":None,
                "g_episode_starts":0,"frontier_events":0}
    prev_g=False; gs=fe=0; p1m=None
    ep=np.floor(am/5.0)*5.0+5.0; last=float(x["minute_abs"].max())
    while ep<=last+1e-12:
        w=x[(x["minute_abs"]>=am-1e-12)&(x["minute_abs"]<=ep+1e-12)]
        if w.empty:break
        cur=float(w.iloc[-1]["close"]); hi=float(w["high"].max())
        broke=((w["minute_abs"]>am+1e-12)&(w["close"].astype(float)<key-1e-9)).any()
        g=cur>prev_close+1e-9; f=hi>prev_hi+1e-9; start=bool(g and not prev_g)
        if start:gs+=1
        if f:fe+=1
        if gs>=2 and fe>=1:
            if broke:
                return {"status":"NO_P1_A1_BROKEN","a1_time":a1t,"p1_time":None,
                        "frontier_time":None,"g_episode_starts":gs,"frontier_events":fe}
            p1m=ep; break
        prev_close=cur; prev_hi=hi; prev_g=g; ep+=5.0
    if p1m is None:
        return {"status":"TRACKING","a1_time":a1t,"p1_time":None,"frontier_time":None,
                "g_episode_starts":gs,"frontier_events":fe}
    p1t=f"{int(p1m//60):02d}:{int(p1m%60):02d}:00"
    post=x[x["minute_abs"]>p1m+1e-12].sort_values("minute_abs",kind="stable")
    if post.empty:
        return {"status":"P1","a1_time":a1t,"p1_time":p1t,"frontier_time":None,
                "g_episode_starts":gs,"frontier_events":fe}
    baseline=post.iloc[0]; runmax=float(baseline["close"]); frontier=None
    for _,r in post.iloc[1:].iterrows():
        c=float(r["close"])
        if c>runmax+1e-12:
            frontier=str(r["time_str"]); break
        runmax=max(runmax,c)
    return {"status":"P1_FRONTIER" if frontier else "P1","a1_time":a1t,"p1_time":p1t,
            "post_p1_entry_time":str(baseline["time_str"]),"post_p1_entry_open":float(baseline["open"]),
            "frontier_time":frontier,"g_episode_starts":gs,"frontier_events":fe}
def prev_trade_date(date):
    # Production-safe: ask Fugle for a small backward window and select latest
    # returned trading date strictly before target; no weekend/holiday guessing.
    return None
def fetch_prev(key,sid,date):
    """
    Resolve the previous trading day from Fugle DAILY candles, but obtain
    prev_close + prev_day_volume from that day's HISTORICAL 1m bars.

    This is deliberate: the frozen AttackVR benchmark was reproduced with
    prior-day 1m volume sum (3714/2026-09-15 = 3593 lots). Fugle daily volume
    is in a different unit/aggregation and MUST NOT be mixed with minute lots.
    """
    d=pd.Timestamp(date)
    start=(d-pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    q=urllib.parse.urlencode({"timeframe":"D","from":start,"to":date,
                              "fields":"open,high,low,close,volume","sort":"asc"})
    u=f"{FUGLE}/historical/candles/{sid}?{q}"
    req=urllib.request.Request(u,headers={"X-API-KEY":key,"Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=TIMEOUT) as r:o=json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        stop(f"Fugle daily-calendar HTTP {e.code}: "+e.read().decode(errors="replace")[:300])
    dates=[]
    for b in o.get("data",[]):
        ds=pd.to_datetime(b["date"]).strftime("%Y-%m-%d")
        if ds<date: dates.append(ds)
    if not dates: stop("No prior trading day found.")
    pdate=max(dates)

    pobj=fetch(key,sid,pdate)
    prows=adapt(pobj,pdate,sid)
    if not prows: stop("Prior trading-day historical 1m bars empty.")
    py=pd.DataFrame(prows).sort_values("minute",kind="stable")
    if py["minute"].duplicated().any(): stop("Prior-day duplicate minute.")
    for c in ["close","volume"]:
        py[c]=pd.to_numeric(py[c],errors="coerce")
    if py[["close","volume"]].isna().any().any(): stop("Prior-day invalid close/volume.")
    pc=float(py.iloc[-1]["close"])
    pv=float(py["volume"].clip(lower=0).sum())
    if pc<=0 or pv<=0: stop("Invalid prior-day 1m close/volume.")
    return pdate,pc,pv

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--date",required=True,help="YYYY-MM-DD")
    ap.add_argument("--discovered-at",required=True,help="HH:MM[:SS], when A handed stock to B")
    ap.add_argument("--dry-run",action="store_true",default=True)
    a=ap.parse_args(); sid=str(a.symbol).zfill(4); date=a.date; disc=nt(a.discovered_at)
    banner(f"FUGLE B ENGINE v3 | {sid} / {date} | discovered_at={disc}")
    print("DRY RUN: no LINE send; no source writes; no backdated execution.")

    # Data Source -> Sample Identity -> Coverage -> Frozen Identity -> Causal Timing
    if not ATTACK.exists() or not EARLY.exists():stop("Required audited source script missing.")
    if sha(ATTACK)!=ATTACK_SHA:stop("Authoritative Attack auditor SHA mismatch.")
    try:
        at=runpy.run_path(str(ATTACK),run_name="__b_attack__")
        er=runpy.run_path(str(EARLY),run_name="__b_early__")
        fa,cc,fe=at["load_attack_engine"]()
        bars_df=er["bars_df"]; reconstruct=er["reconstruct_a2"]; replay=er["replay_early"]
    except BaseException as e:stop(f"Frozen implementation load failed: {e!r}")
    print("[1] DATA SOURCE / FROZEN CODE IDENTITY: PASS")

    key,ks=find_key(); t=time.perf_counter()
    day=fetch(key,sid,date); pdate,pc,pv=fetch_prev(key,sid,date)
    d=bars_df(adapt(day,date,sid),date,sid)
    if d.empty or d.time_str.duplicated().any() or not d.minute_abs.is_monotonic_increasing:stop("Minute coverage/order failed.")
    print(f"[2] SAMPLE IDENTITY: PASS | {sid} {date}")
    print(f"[3] COVERAGE: PASS | rows={len(d)} {d.iloc[0].time_str}->{d.iloc[-1].time_str} | prior={pdate} close={pc} volume={pv:g}")
    if sid=="3714" and date=="2026-09-16":
        if pdate!="2026-09-15" or abs(pc-60.1)>1e-12 or abs(pv-3593.0)>1e-12:
            stop(f"3714 benchmark prior-context mismatch: prior={pdate}, close={pc}, volume={pv}; expected 2026-09-15 / 60.1 / 3593")
        print("    benchmark prior-context audit: PASS (60.1 / 3593 lots)")
    print(f"    Fugle latency={time.perf_counter()-t:.3f}s | key=<REDACTED> ({ks})")

    # Critical production causality: B may replay only data available through discovery.
    cutoff=d[d.time_str<=disc].copy()
    if cutoff.empty:stop("No market minute available at/before discovery.")
    print(f"    replay cutoff={cutoff.iloc[-1].time_str} (nothing after discovery enters recognition replay)")

    rec=reconstruct(cutoff,pc,pv,fa,cc,fe)
    print("\n[4] FROZEN IDENTITY / ATTACK")
    for k in ["key_price","early_high_pct","attack_count","a1_end","a2_start","a2_end","a2_vr","a2_upward"]:
        print(f"    {k:18s}: {rec.get(k)}")
    if int(rec.get("attack_count",0))<2:
        print("\nSTATE: TRACKING | A2 not yet established by live-known cutoff."); return
    if not rec.get("a2_upward"):
        print("\nSTATE: NO_SIGNAL | A2 is not Upward."); return

    typ=abc(float(rec.get("a2_vr",np.nan)),float(rec.get("early_high_pct",np.nan)))
    print(f"    ABC candidate      : {typ}")
    if typ=="NO_BUY":
        print("\nSTATE: NO_SIGNAL | fixed A/B/C VR?EarlyHigh cells not met."); return

    early=replay(cutoff,rec["a2_end"])
    print("\n[5] CAUSAL TIMING / FROZEN EARLY")
    print(f"    status             : {early.get('early_status')}")
    print(f"    recognition_time   : {early.get('early_time')}")
    if early.get("early_status")!="EARLY":
        print("\nSTATE: TRACKING | A/B/C candidate exists, Frozen Early not yet established by live-known cutoff."); return

    recognition=nt(early["early_time"])
    # live-known cannot precede either discovery or recognition.
    live_known=disc if mins(disc)>=mins(recognition) else recognition
    # Execution = first observed minute after live-known, using the fetched day only
    # for dry-run validation. In actual live mode this must wait for that future bar.
    future=d[d.minute_abs>mins(live_known)+EPS].sort_values("minute_abs")
    execution_time=""; execution_open=np.nan
    if not future.empty:
        r=future.iloc[0]; execution_time=str(r.time_str); execution_open=float(r.open)

    event={
        "schema":"b_signal_event_v1","date":date,"stock_id":sid,"signal_class":typ,
        "discovered_at":disc,"recognition_time":recognition,"live_known_time":live_known,
        "a2_end":rec.get("a2_end"),"a2_vr":float(rec["a2_vr"]),
        "early_high_pct":float(rec["early_high_pct"]),
        "frozen_early_price":float(early.get("early_price")),
        "execution_policy":"first observed minute OPEN strictly after live_known_time",
        "execution_time":execution_time or None,
        "execution_open":None if not np.isfinite(execution_open) else execution_open,
        "late_discovery":bool(mins(disc)>mins(recognition)),
        "source":"Fugle","dry_run":True
    }
    OUT.mkdir(parents=True,exist_ok=True)
    fp=OUT/f"{date}_{sid}_{disc.replace(':','')}_signal_event.json"
    fp.write_text(json.dumps(event,ensure_ascii=False,indent=2),encoding="utf-8")

    banner("SIGNAL EVENT")
    print(json.dumps(event,ensure_ascii=False,indent=2))
    print("\nSaved:",fp)
    print("\nB ENGINE v3: ABC PRODUCTION-SEMANTIC DRY-RUN PASS")
    print("No LINE notification was sent.")

if __name__=="__main__":main()