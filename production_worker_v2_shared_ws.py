# -*- coding: utf-8 -*-
"""Trend production worker v2: A 5s -> in-process B runners -> ONE shared Fugle WS."""
from __future__ import annotations
import argparse,json,os,queue,runpy,sys,threading,time
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo
from twse_session_gate_v1 import is_scheduled_open
from group_limit_up import monitor_loop as group_limit_up_monitor_loop

BASE=Path(__file__).resolve().parent
A=BASE/"fugle_a_scanner_v2_4.py"; BR=BASE/"fugle_b_live_runner_v2_p1_final.py"
TPE=ZoneInfo("Asia/Taipei"); HOST="127.0.0.1"; PORT=int(os.environ.get("TREND_HANDOFF_PORT","8765"))
LINE_SEND=os.environ.get("TREND_LINE_SEND","0").strip().lower() in {"1","true","yes","on"}
STATE_ROOT=Path(os.environ.get("PRODUCTION_STATE_DIR",str(BASE/"_production_output")))
_lock=threading.RLock(); _runners={}; _queues={}; _launching=set(); _subscribed=set(); _ws_app=None; _ws_ready=False
_last_ws_minute={}; _last_ws_fingerprint={}; _last_overflow_log={}
_f14_done=set(); _f14_day=None; _f14_path=None

def now_tpe(): return datetime.now(TPE)

def _atomic_json(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8")
    tmp.replace(path)

def f14_bootstrap(day):
    global _f14_day,_f14_path
    day=str(day)[:10];root=STATE_ROOT/"f14_done";root.mkdir(parents=True,exist_ok=True)
    path=root/f"{day}.json";done=set()
    if path.exists():
        x=json.loads(path.read_text(encoding="utf-8"))
        if x.get("schema")!="f14_done_v1" or x.get("date")!=day:raise RuntimeError("F14 registry identity/schema mismatch")
        done={key(day,s) for s in x.get("stock_ids",[])}
    bday=STATE_ROOT/"b_live_runner_v2_p1"/day
    if bday.is_dir():
        for sd in bday.iterdir():
            if not sd.is_dir():continue
            sid=sd.name.zfill(4)
            for fn in ("signal_event.json","p1_signal_event.json"):
                ep=sd/fn
                if not ep.is_file():continue
                try:e=json.loads(ep.read_text(encoding="utf-8"))
                except Exception as ex:
                    raise RuntimeError(f"F14 authoritative event unreadable: {ep}: {ex!r}") from ex
                if e.get("date")==day and str(e.get("stock_id","")).zfill(4)==sid and e.get("line_sent") is True:
                    done.add(key(day,sid));break
    with _lock:
        _f14_done.clear();_f14_done.update(done);_f14_day=day;_f14_path=path
    _atomic_json(path,{"schema":"f14_done_v1","date":day,"stock_ids":sorted(x.split("|")[1] for x in done)})
    print(f"[F14 BOOTSTRAP] date={day} DONE={len(done)}",flush=True)

def f14_mark_done(k):
    with _lock:
        if _f14_day!=k.split("|",1)[0]:raise RuntimeError(f"F14 day mismatch loaded={_f14_day} key={k}")
        _f14_done.add(k)
        _atomic_json(_f14_path,{"schema":"f14_done_v1","date":_f14_day,"stock_ids":sorted(x.split("|")[1] for x in _f14_done)})
    print(f"[F14 DONE] {k}",flush=True)

def f14_ensure_day(day):
    day=str(day)[:10]
    with _lock:
        if _f14_day==day:return
        # Same lifecycle lock: exactly one rollover bootstrap; no half-switched DONE/CLAIM state.
        f14_bootstrap(day)

def retire_runner(k,r=None):
    sid=k.split("|",1)[1]
    if r is not None:r.retired=True
    with _lock:
        if r is not None and _runners.get(k) is not r: return
        q=_queues.pop(k,None);_runners.pop(k,None);_launching.discard(k);_subscribed.discard(sid)
        _last_ws_minute.pop(k,None);_last_ws_fingerprint.pop(k,None);_last_overflow_log.pop(k,None)
    if q is not None:
        try:q.put_nowait(None)
        except Exception:pass
    print(f"[B RETIRE] {k} successful LINE -> runtime released",flush=True)
def key(day,sid): return f"{day}|{str(sid).zfill(4)}"
def ws_fingerprint(row): return (row["minute"],row["open"],row["high"],row["low"],row["close"],row["volume"])

def preflight():
    need=[A,BR,BASE/"fugle_b_engine_v2_p1.py",BASE/"fugle_b_data_adapter_v1.py",
          BASE/"run_strong_x_frozen_trend_live_auditor_v4.py",BASE/"audit_strong_4day_frozen_early_abc_buy_2026_v1.py",
          BASE/"backend/events/attack_engine.py",BASE/"line_signal_notifier_v2.py"]
    miss=[x.name for x in need if not x.is_file()]
    if miss: raise RuntimeError("missing production files: "+", ".join(miss))
    if not os.environ.get("FUGLE_API_KEY","").strip(): raise RuntimeError("FUGLE_API_KEY missing")
    if LINE_SEND and not (os.environ.get("LINE_TOKEN","").strip() or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN","").strip()):
        raise RuntimeError("LINE token missing")
    if LINE_SEND and not (os.environ.get("GROUP_ID","").strip() or os.environ.get("LINE_TO_ID","").strip()):
        raise RuntimeError("LINE destination missing")

def runner_module(): return runpy.run_path(str(BR),run_name="__shared_b_runner__")

def worker_loop(k,r,q):
    while True:
        item=q.get()
        if item is None:return
        try:
            with r.lock:
                a,c,d=r.merge([item],"ws")
                if r.first_ws_candle is None:r.first_ws_candle=item["minute"]
                r.last_ws_candle=item["minute"]
                r.evaluate_completed("shared_websocket_completed_minute")
            with _lock:
                if k in _runners and not getattr(r,"retired",False):
                    _last_ws_minute[k]=item["minute"];_last_ws_fingerprint[k]=ws_fingerprint(item)
                else:return
        except BaseException as e:
            print(f"[B FAIL CLOSED] {k} {type(e).__name__}: {e}; runner disabled",flush=True)
            with _lock:_runners.pop(k,None);_queues.pop(k,None)
            return

def launch_b(payload,dry_run=False):
    for x in ("stock_id","date","discovered_at"):
        if not payload.get(x): raise ValueError("missing: "+x)
    sid=str(payload["stock_id"]).zfill(4); day=str(payload["date"])[:10]; disc=str(payload["discovered_at"]); stock_name=str(payload.get("name") or payload.get("stock_name") or "").strip(); k=key(day,sid)
    f14_ensure_day(day)
    with _lock:
        if k in _f14_done:
            print(f"[F14 SKIP DONE] {k} before Runner construction",flush=True)
            return {"ok":True,"already_done":True,"launched":False,"key":k}
        if k in _runners or k in _launching:
            return {"ok":True,"duplicate":True,"launched":False,"key":k}
        if not dry_run:
            _launching.add(k)
    if dry_run:return {"ok":True,"duplicate":False,"launched":False,"dry_run":True,"key":k}
    try:
        M=runner_module(); R=M["Runner"]
        r=None
        def on_line_sent(path,label,event):
            f14_mark_done(k);retire_runner(k,r)
        r=R(sid,day,disc,0,line_send=LINE_SEND,stock_name=stock_name,on_line_sent=on_line_sent)
        r.rest_reconcile("startup")
        if getattr(r,"retired",False):
            with _lock:_launching.discard(k)
            return {"ok":True,"already_done":True,"launched":False,"key":k,"line_completed_during_startup":True}
        q=queue.Queue(maxsize=2000)
        with _lock:
            _runners[k]=r;_queues[k]=q;_launching.discard(k)
        threading.Thread(target=worker_loop,args=(k,r,q),daemon=True).start()
        subscribe_symbol(sid)
        print(f"[B START] {k} shared-WS LINE={'ON' if LINE_SEND else 'DRY'}",flush=True)
        return {"ok":True,"duplicate":False,"launched":True,"key":k,"shared_ws":True}
    except BaseException:
        with _lock:_launching.discard(k)
        raise

def subscribe_symbol(sid):
    global _ws_app,_ws_ready
    with _lock:
        if sid in _subscribed:return
        app=_ws_app
        if app is not None and _ws_ready:
            app.send(json.dumps({"event":"subscribe","data":{"channel":"candles","symbol":sid}}))
            _subscribed.add(sid); print(f"[SHARED WS SUBSCRIBE] {sid}",flush=True)

def route_message(msg):
    try:o=json.loads(msg)
    except:return
    ev=str(o.get("event","")) if isinstance(o,dict) else ""
    if ev in ("error","server_error"):
        print("[SHARED WS SERVER ERROR] "+str(o)[:300],flush=True);return
    if ev=="authenticated":
        global _ws_ready
        with _lock:
            _ws_ready=True
            syms=sorted({k.split("|")[1] for k in _runners})
            for sid in syms:
                _ws_app.send(json.dumps({"event":"subscribe","data":{"channel":"candles","symbol":sid}}))
                _subscribed.add(sid)
        print(f"[SHARED WS] authenticated; subscriptions={len(syms)}",flush=True);return
    stack=[o]
    while stack:
        x=stack.pop()
        if isinstance(x,list):stack.extend(x);continue
        if not isinstance(x,dict):continue
        for z in ("data","candle","candles"):
            if z in x:stack.append(x[z])
        sid=str(x.get("symbol") or x.get("code") or "")
        if not sid or not all(z in x for z in ("open","high","low","close","volume")):continue
        raw=x.get("date") or x.get("time") or x.get("timestamp")
        if raw is None:continue
        try:
            import pandas as pd
            if isinstance(raw,(int,float)):
                dt=pd.to_datetime(raw,unit="ms" if raw>10**11 else "s",utc=True).tz_convert("Asia/Taipei")
            else:
                dt=pd.to_datetime(raw)
                if dt.tzinfo is not None:dt=dt.tz_convert("Asia/Taipei")
            day=dt.strftime("%Y-%m-%d"); minute=dt.strftime("%H:%M:00")
        except:return
        k=key(day,sid)
        with _lock:q=_queues.get(k)
        if q is None:return
        row={"date":day,"stock_id":sid,"minute":minute,"open":x["open"],"high":x["high"],"low":x["low"],"close":x["close"],"volume":x["volume"]}
        # Coalesce repeated Fugle revisions of the same stock+minute. B consumes
        # completed-minute state; exact duplicates can be dropped, but a changed
        # same-minute OHLCV revision must reach Runner.merge() for reconciliation.
        with _lock:
            if _last_ws_minute.get(k)==minute and _last_ws_fingerprint.get(k)==ws_fingerprint(row):return
        with q.mutex:
            for i in range(len(q.queue)-1,-1,-1):
                z=q.queue[i]
                if isinstance(z,dict) and z.get("minute")==minute:
                    q.queue[i]=row
                    return
        try:q.put_nowait(row)
        except queue.Full:
            now=time.monotonic(); last=_last_overflow_log.get(k,0.0)
            if now-last>=5.0:
                _last_overflow_log[k]=now
                print(f"[B FAIL CLOSED] {k} queue overflow size={q.qsize()}; NO PRODUCTION SIGNAL",flush=True)
        return

def shared_ws_loop():
    global _ws_app,_ws_ready
    import websocket
    M=runner_module(); dummy_url=M["Runner"].ws_url
    # recover the same audited WS URL without constructing a Runner
    import re
    txt=(BASE/"fugle_b_data_adapter_v1.py").read_text(encoding="utf-8",errors="ignore")
    urls=re.findall(r'wss://[^"\']+',txt)
    if not urls:raise RuntimeError("Cannot recover proven Fugle WS URL")
    url=urls[0]; api=os.environ["FUGLE_API_KEY"].strip(); backoff=2
    while True:
        with _lock:_subscribed.clear();_ws_ready=False
        def on_open(ws):ws.send(json.dumps({"event":"auth","data":{"apikey":api}}))
        def on_message(ws,msg):route_message(msg)
        def on_error(ws,e):print("[SHARED WS ERROR] "+repr(e),flush=True)
        def on_close(ws,*a):print("[SHARED WS] closed",flush=True)
        app=websocket.WebSocketApp(url,on_open=on_open,on_message=on_message,on_error=on_error,on_close=on_close)
        with _lock:_ws_app=app
        app.run_forever()
        with _lock:_ws_app=None;_ws_ready=False
        # Before resubscribe, reconcile every active B from completed REST bars.
        with _lock:rs=list(_runners.items())
        for k,r in rs:
            try:
                with r.lock:
                    if getattr(r,"retired",False):continue
                    r.rest_reconcile("reconnect")
            except BaseException as e:print(f"[B RECONCILE FAIL CLOSED] {k}: {e}",flush=True)
        time.sleep(backoff);backoff=min(backoff*2,30)

def clock_loop():
    while True:
        with _lock:rs=list(_runners.items())
        for k,r in rs:
            try:
                with r.lock:
                    if getattr(r,"retired",False):continue
                    r.evaluate_completed("shared_clock_completed_minute")
            except BaseException as e:print(f"[B CLOCK FAIL CLOSED] {k}: {e}",flush=True)
        time.sleep(1)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):return
    def sendj(self,n,o):
        b=json.dumps(o,ensure_ascii=False).encode();self.send_response(n);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_POST(self):
        if self.path!="/discovery":return self.sendj(404,{"ok":False})
        # Keep launch failure separate from response-socket failure. Once
        # launch_b() returns, B has already been created/subscribed; a caller
        # disconnect while writing HTTP 200 must not be mislabeled fail-closed.
        try:
            n=int(self.headers.get("Content-Length","0"))
            result=launch_b(json.loads(self.rfile.read(n)))
        except BaseException as e:
            print(f"[BRIDGE FAIL CLOSED] {type(e).__name__}: {e}",flush=True)
            try:self.sendj(400,{"ok":False,"error":f"{type(e).__name__}: {e}"})
            except (BrokenPipeError,ConnectionResetError):
                print("[BRIDGE RESPONSE DROPPED] caller disconnected after launch failure",flush=True)
            return
        try:self.sendj(200,result)
        except (BrokenPipeError,ConnectionResetError) as e:
            print(f"[BRIDGE RESPONSE DROPPED] B launch already succeeded: {type(e).__name__}: {e}",flush=True)

def serve():ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

def wait_session():
    while True:
        n=now_tpe()
        if n.time()<n.replace(hour=9,minute=0,second=0,microsecond=0).time():
            print(f"[SESSION WAIT] {n.date()} before 09:00; NO PRODUCTION SIGNAL",flush=True);time.sleep(300);continue
        if n.time()>=n.replace(hour=13,minute=30,second=0,microsecond=0).time():
            print(f"[SESSION CLOSED] {n.date()} after 13:30; NO PRODUCTION SIGNAL",flush=True);time.sleep(1800);continue
        try:
            if is_scheduled_open(n.date()):return
            print(f"[SESSION CLOSED] {n.date()} TWSE official schedule; NO PRODUCTION SIGNAL",flush=True)
        except Exception as e:print(f"[SESSION AUDIT FAILED] {e}; NO PRODUCTION SIGNAL",flush=True)
        time.sleep(300)

def f10_maintenance_loop():
    """Legacy F10 maintenance remains available only when sequential staging mode is OFF."""
    import subprocess
    if os.environ.get("A_DAILY_HISTORY_MAINTENANCE_ENABLED","0").strip()=="1":
        print("[F10 MAINT] managed by sequential daily updater; legacy thread disabled",flush=True)
        return
    script=BASE/"f10_baseline_store_v1.py"
    last_attempt_day=None
    first=True
    while True:
        n=now_tpe()
        after_close=(n.hour,n.minute)>=(14,30)
        should=first or (after_close and last_attempt_day!=n.date().isoformat())
        if should:
            mode="update" if after_close else "init"
            print(f"[F10 MAINT] start mode={mode}",flush=True)
            try:
                rc=subprocess.call([sys.executable,str(script),"--mode",mode,"--pause","0.15"],cwd=str(BASE),env=os.environ.copy())
                print(f"[F10 MAINT] done mode={mode} rc={rc}",flush=True)
            except BaseException as e:
                print(f"[F10 MAINT FAIL] {type(e).__name__}: {e}",flush=True)
            if after_close:last_attempt_day=n.date().isoformat()
            first=False
        time.sleep(60)

def daily_history_maintenance_loop():
    """Opt-in sequential 15:30 maintenance: daily K -> F10, retry failed stage in 30 min."""
    import subprocess
    if os.environ.get("A_DAILY_HISTORY_MAINTENANCE_ENABLED","0").strip()!="1":
        print("[A DAILY HISTORY MAINT] disabled (default)",flush=True)
        return
    daily=BASE/"research"/"a_daily_incremental_maintenance_v1.py"
    f10=BASE/"f10_baseline_store_v1.py"
    metadata_gate=BASE/"research"/"a_f11_f12_staging_coverage_gate_v1.py"
    completed_day=None
    next_retry_at=0.0
    while True:
        n=now_tpe()
        day=n.date().isoformat()
        if (n.hour,n.minute)>=(15,30) and completed_day!=day and time.monotonic()>=next_retry_at:
            try:
                if not is_scheduled_open(n.date()):
                    completed_day=day
                elif not daily.is_file() or not f10.is_file() or not metadata_gate.is_file():
                    print("[SEQUENTIAL MAINT] script missing; retry in 30m",flush=True)
                    next_retry_at=time.monotonic()+1800
                else:
                    # Daily K is resumable; successful reruns use coverage and make zero API calls.
                    tasks=(("DAILY_K",[sys.executable,str(daily),"--execute"]),
                           ("F10",[sys.executable,str(f10),"--mode","update","--pause","0.15"]),
                           ("F11_F12_CHECK",[sys.executable,str(metadata_gate)]))
                    for name,cmd in tasks:
                        print(f"[SEQUENTIAL MAINT] {name} start date={day}",flush=True)
                        rc=subprocess.call(cmd,cwd=str(BASE),env=os.environ.copy())
                        if rc!=0:
                            print(f"[SEQUENTIAL MAINT] {name} incomplete rc={rc}; later stages blocked",flush=True)
                            break
                        print(f"[SEQUENTIAL MAINT] {name} completed",flush=True)
                    else:
                        completed_day=day
                        print(f"[SEQUENTIAL MAINT] ALL COMPLETED date={day}",flush=True)
                        time.sleep(60)
                        continue
                    next_retry_at=time.monotonic()+1800
            except BaseException as exc:
                next_retry_at=time.monotonic()+1800
                print(f"[SEQUENTIAL MAINT] FAIL {type(exc).__name__}: {exc}; retry in 30m",flush=True)
        time.sleep(60)

def self_test():
    assert launch_b({"stock_id":"3714","date":"2026-09-29","discovered_at":"10:22:05"},True)["dry_run"]
    assert key("2026-09-29","2330")=="2026-09-29|2330"
    q1=queue.Queue();q2=queue.Queue()
    _queues["2026-09-29|3714"]=q1;_queues["2026-09-29|2330"]=q2
    synthetic={"data":{"symbol":"3714","date":"2026-09-29T10:23:00+08:00","open":10,"high":11,"low":9,"close":10.5,"volume":100}}
    route_message(json.dumps(synthetic))
    assert q1.qsize()==1 and q2.qsize()==0
    got=q1.get_nowait();assert got["stock_id"]=="3714" and got["minute"]=="10:23:00"
    _queues.clear()
    print("[PASS] shared manager payload/dedupe key")
    print("[PASS] synthetic candle routed to correct symbol only; no cross-stock contamination")
    print("[PASS] self-test opens NO network, sends NO LINE, creates NO runner")
    print("NO PRODUCTION SIGNAL")

def a_launch_gate_once(snapshot_day, verify=None):
    """Pure decision boundary for A launch; caller handles retry and subprocess."""
    if verify is None:
        from a_history_preflight_v1 import verify_a_history
        verify=verify_a_history
    required=verify(snapshot_day)
    if not required or str(required) >= str(snapshot_day):
        raise RuntimeError("A history preflight returned invalid last completed session")
    env=os.environ.copy()
    env["A_LAST_COMPLETED_SESSION"]=str(required)
    env["A_VERIFIED_SNAPSHOT_DAY"]=str(snapshot_day)
    return env

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--self-test",action="store_true");a=ap.parse_args()
    if a.self_test:self_test();return
    self_test()
    preflight();STATE_ROOT.mkdir(parents=True,exist_ok=True);f14_bootstrap(now_tpe().date().isoformat());threading.Thread(target=f10_maintenance_loop,name="f10-maint",daemon=True).start();threading.Thread(target=daily_history_maintenance_loop,name="a-daily-maint",daemon=True).start();wait_session()
    threading.Thread(target=serve,daemon=True).start()
    threading.Thread(target=shared_ws_loop,daemon=True).start()
    threading.Thread(target=clock_loop,daemon=True).start()
    threading.Thread(
        target=group_limit_up_monitor_loop,
        args=(os.environ.get("LINE_TOKEN", "").strip(), os.environ.get("GROUP_ID", "").strip()),
        name="group-limit-up-monitor",
        daemon=True,
    ).start()
    print("[GROUP LIMIT-UP] monitor started | source=TWSE MIS",flush=True)
    bridge=f"http://{HOST}:{PORT}/discovery"
    print("="*92);print("TREND PRODUCTION WORKER v2 | ONE SHARED WS | A=5s | P1/A/B/C | LINE="+("ON" if LINE_SEND else "DRY"));print("="*92)
    import subprocess
    while True:
        # A daily history preflight: one official calendar fetch per launch.
        # Fail closed BEFORE starting A, preventing mass WAIT_DATA/Fugle fallback.
        try:
            a_env=a_launch_gate_once(now_tpe().date().isoformat())
        except Exception as exc:
            print(f"[A HISTORY PREFLIGHT BLOCKED] {type(exc).__name__}: {exc}; NO A LAUNCH",flush=True)
            time.sleep(60)
            continue
        print(f"[A HISTORY PREFLIGHT PASS] last_completed={a_env['A_LAST_COMPLETED_SESSION']}",flush=True)
        p=subprocess.Popen([sys.executable,str(A),"--interval","5","--bridge-url",bridge],cwd=str(BASE),env=a_env)
        rc=p.wait();print(f"[A EXIT] rc={rc}; restart in 10s",flush=True);time.sleep(10)

if __name__=="__main__":main()
