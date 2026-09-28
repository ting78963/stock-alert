# -*- coding: utf-8 -*-
"""Trend production worker v2: A 5s -> in-process B runners -> ONE shared Fugle WS."""
from __future__ import annotations
import argparse,json,os,queue,runpy,sys,threading,time
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo
from twse_session_gate_v1 import is_scheduled_open

BASE=Path(__file__).resolve().parent
A=BASE/"fugle_a_scanner_v2_2.py"; BR=BASE/"fugle_b_live_runner_v2_p1_final.py"
TPE=ZoneInfo("Asia/Taipei"); HOST="127.0.0.1"; PORT=int(os.environ.get("TREND_HANDOFF_PORT","8765"))
LINE_SEND=os.environ.get("TREND_LINE_SEND","0").strip().lower() in {"1","true","yes","on"}
STATE_ROOT=Path(os.environ.get("PRODUCTION_STATE_DIR",str(BASE/"_production_output")))
_lock=threading.RLock(); _runners={}; _queues={}; _subscribed=set(); _ws_app=None; _ws_ready=False

def now_tpe(): return datetime.now(TPE)
def key(day,sid): return f"{day}|{str(sid).zfill(4)}"

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
        except BaseException as e:
            print(f"[B FAIL CLOSED] {k} {type(e).__name__}: {e}; runner disabled",flush=True)
            with _lock:_runners.pop(k,None);_queues.pop(k,None)
            return

def launch_b(payload,dry_run=False):
    for x in ("stock_id","date","discovered_at"):
        if not payload.get(x): raise ValueError("missing: "+x)
    sid=str(payload["stock_id"]).zfill(4); day=str(payload["date"])[:10]; disc=str(payload["discovered_at"]); k=key(day,sid)
    with _lock:
        if k in _runners:return {"ok":True,"duplicate":True,"launched":False,"key":k}
    if dry_run:return {"ok":True,"duplicate":False,"launched":False,"dry_run":True,"key":k}
    M=runner_module(); R=M["Runner"]
    r=R(sid,day,disc,0,line_send=LINE_SEND)
    r.rest_reconcile("startup")
    q=queue.Queue(maxsize=2000)
    with _lock:_runners[k]=r;_queues[k]=q
    threading.Thread(target=worker_loop,args=(k,r,q),daemon=True).start()
    subscribe_symbol(sid)
    print(f"[B START] {k} shared-WS LINE={'ON' if LINE_SEND else 'DRY'}",flush=True)
    return {"ok":True,"duplicate":False,"launched":True,"key":k,"shared_ws":True}

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
        try:q.put_nowait(row)
        except queue.Full:
            print(f"[B FAIL CLOSED] {k} queue overflow; NO PRODUCTION SIGNAL",flush=True)
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
                with r.lock:r.rest_reconcile("reconnect")
            except BaseException as e:print(f"[B RECONCILE FAIL CLOSED] {k}: {e}",flush=True)
        time.sleep(backoff);backoff=min(backoff*2,30)

def clock_loop():
    while True:
        with _lock:rs=list(_runners.items())
        for k,r in rs:
            try:
                with r.lock:r.evaluate_completed("shared_clock_completed_minute")
            except BaseException as e:print(f"[B CLOCK FAIL CLOSED] {k}: {e}",flush=True)
        time.sleep(1)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):return
    def sendj(self,n,o):
        b=json.dumps(o,ensure_ascii=False).encode();self.send_response(n);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_POST(self):
        if self.path!="/discovery":return self.sendj(404,{"ok":False})
        try:n=int(self.headers.get("Content-Length","0"));self.sendj(200,launch_b(json.loads(self.rfile.read(n))))
        except Exception as e:self.sendj(400,{"ok":False,"error":f"{type(e).__name__}: {e}"})

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

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--self-test",action="store_true");a=ap.parse_args()
    if a.self_test:self_test();return
    self_test()
    preflight();wait_session();STATE_ROOT.mkdir(parents=True,exist_ok=True)
    threading.Thread(target=serve,daemon=True).start()
    threading.Thread(target=shared_ws_loop,daemon=True).start()
    threading.Thread(target=clock_loop,daemon=True).start()
    bridge=f"http://{HOST}:{PORT}/discovery"
    print("="*92);print("TREND PRODUCTION WORKER v2 | ONE SHARED WS | A=5s | P1/A/B/C | LINE="+("ON" if LINE_SEND else "DRY"));print("="*92)
    import subprocess
    while True:
        p=subprocess.Popen([sys.executable,str(A),"--interval","5","--bridge-url",bridge],cwd=str(BASE),env=os.environ.copy())
        rc=p.wait();print(f"[A EXIT] rc={rc}; restart in 10s",flush=True);time.sleep(10)

if __name__=="__main__":main()
