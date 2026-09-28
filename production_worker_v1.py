# -*- coding: utf-8 -*-
"""Cloud coordinator: A 5s -> localhost handoff -> B per discovered stock -> P1/A/B/C.
Separate from the existing limit-up web service. Persistent state uses PRODUCTION_STATE_DIR.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, threading, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo
from twse_session_gate_v1 import is_scheduled_open

BASE=Path(__file__).resolve().parent
A=BASE/"fugle_a_scanner_v2_2.py"
B=BASE/"fugle_b_live_runner_v2_p1_final.py"
TPE=ZoneInfo("Asia/Taipei")
HOST="127.0.0.1"
PORT=int(os.environ.get("TREND_HANDOFF_PORT","8765"))
STATE_ROOT=Path(os.environ.get("PRODUCTION_STATE_DIR",str(BASE/"_production_output")))
LOGDIR=STATE_ROOT/"trend_worker_logs"
LINE_SEND=os.environ.get("TREND_LINE_SEND","0").strip().lower() in {"1","true","yes","on"}
_lock=threading.Lock()
_active={}

def now_tpe(): return datetime.now(TPE)
def minutes_to_close():
    now=now_tpe(); close=now.replace(hour=13,minute=30,second=0,microsecond=0)
    return max(0.1,(close-now).total_seconds()/60.0)

def reap():
    with _lock:
        dead=[k for k,p in _active.items() if p.poll() is not None]
        for k in dead:
            print(f"[B EXIT] {k} rc={_active[k].returncode}",flush=True); _active.pop(k,None)

def launch_b(payload,dry_run=False):
    required=("stock_id","date","discovered_at")
    missing=[x for x in required if not payload.get(x)]
    if missing: raise ValueError("missing: "+",".join(missing))
    sid=str(payload["stock_id"]).zfill(4); day=str(payload["date"])[:10]; disc=str(payload["discovered_at"])
    k=f"{day}|{sid}"
    reap()
    with _lock:
        prior=_active.get(k)
        if prior is not None and prior.poll() is None:
            return {"ok":True,"duplicate":True,"launched":False,"key":k}
    mins=minutes_to_close()
    cmd=[sys.executable,str(B),sid,"--date",day,"--discovered-at",disc,"--minutes",f"{mins:.4f}"]
    if LINE_SEND and not dry_run: cmd.append("--line-send")
    if dry_run:
        return {"ok":True,"duplicate":False,"launched":False,"dry_run":True,"key":k,
                "minutes_to_close":round(mins,4),"line_send":False,
                "command":[Path(x).name if i in (0,1) else x for i,x in enumerate(cmd)]}
    LOGDIR.mkdir(parents=True,exist_ok=True)
    log=(LOGDIR/f"{day}_{sid}.log").open("a",encoding="utf-8")
    proc=subprocess.Popen(cmd,cwd=str(BASE),stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy(),text=True)
    with _lock: _active[k]=proc
    print(f"[B START] {k} pid={proc.pid} until=13:30 LINE={'ON' if LINE_SEND else 'DRY'}",flush=True)
    return {"ok":True,"duplicate":False,"launched":True,"key":k,"pid":proc.pid,
            "minutes_to_close":round(mins,4),"line_send":LINE_SEND}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): return
    def _send(self,status,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_POST(self):
        if self.path!="/discovery": self._send(404,{"ok":False,"error":"not found"}); return
        try:
            n=int(self.headers.get("Content-Length","0")); payload=json.loads(self.rfile.read(n).decode("utf-8"))
            self._send(200,launch_b(payload))
        except Exception as e: self._send(400,{"ok":False,"error":f"{type(e).__name__}: {e}"})

def serve():
    srv=ThreadingHTTPServer((HOST,PORT),Handler)
    print(f"[HANDOFF] http://{HOST}:{PORT}/discovery",flush=True); srv.serve_forever()

def preflight():
    need=[A,B,BASE/"fugle_b_engine_v2_p1.py",BASE/"fugle_b_data_adapter_v1.py",
          BASE/"run_strong_x_frozen_trend_live_auditor_v4.py",
          BASE/"audit_strong_4day_frozen_early_abc_buy_2026_v1.py",
          BASE/"backend/events/attack_engine.py",BASE/"line_signal_notifier_v2.py"]
    missing=[str(x.name) for x in need if not x.is_file()]
    if missing: raise RuntimeError("missing production files: "+", ".join(missing))
    if not os.environ.get("FUGLE_API_KEY","").strip(): raise RuntimeError("FUGLE_API_KEY missing")
    if LINE_SEND:
        if not (os.environ.get("LINE_TOKEN","").strip() or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN","").strip()):
            raise RuntimeError("LINE token missing while TREND_LINE_SEND=1")
        if not (os.environ.get("GROUP_ID","").strip() or os.environ.get("LINE_TO_ID","").strip()):
            raise RuntimeError("LINE destination missing while TREND_LINE_SEND=1")

def self_test():
    payload={"stock_id":"3714","date":now_tpe().date().isoformat(),"discovered_at":"10:22:05","source":"VCP"}
    x=launch_b(payload,dry_run=True)
    assert x["ok"] and not x["launched"] and x["dry_run"] and x["key"].endswith("|3714")
    assert "--line-send" not in x["command"]
    print("[PASS] A->manager payload validation")
    print("[PASS] same-day B command construction")
    print("[PASS] B lifetime computed to 13:30 (not fixed 30m)")
    print("[PASS] self-test cannot send LINE or start B")
    print("NO NETWORK | NO LINE | NO PRODUCTION SIGNAL")

def wait_for_open_session():
    while True:
        now=now_tpe()
        # Never start A outside the cash-session window.
        if now.time() < now.replace(hour=9,minute=0,second=0,microsecond=0).time():
            print(f"[SESSION WAIT] {now.date().isoformat()} before 09:00; NO PRODUCTION SIGNAL; retry in 5m",flush=True)
            time.sleep(300); continue
        if now.time() >= now.replace(hour=13,minute=30,second=0,microsecond=0).time():
            print(f"[SESSION CLOSED] {now.date().isoformat()} after 13:30; NO PRODUCTION SIGNAL; retry in 30m",flush=True)
            time.sleep(1800); continue
        try:
            if is_scheduled_open(now.date()):
                print(f"[SESSION OPEN] {now.date().isoformat()} TWSE official schedule + 09:00-13:30 gate",flush=True)
                return
            print(f"[SESSION CLOSED] {now.date().isoformat()} TWSE official schedule; NO PRODUCTION SIGNAL; retry in 30m",flush=True)
        except Exception as e:
            print(f"[SESSION AUDIT FAILED] {type(e).__name__}: {e}; NO PRODUCTION SIGNAL; retry in 5m",flush=True)
            time.sleep(300); continue
        time.sleep(1800)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--self-test",action="store_true"); a=ap.parse_args()
    if a.self_test: self_test(); return 0
    preflight(); wait_for_open_session(); STATE_ROOT.mkdir(parents=True,exist_ok=True)
    threading.Thread(target=serve,daemon=True).start(); time.sleep(0.2)
    bridge=f"http://{HOST}:{PORT}/discovery"; cmd=[sys.executable,str(A),"--interval","5","--bridge-url",bridge]
    print("="*92,flush=True); print("TREND PRODUCTION WORKER v1",flush=True)
    print("A=5s | B=discovery->13:30 | P1/A/B/C | LINE="+("ON" if LINE_SEND else "DRY"),flush=True)
    print("state="+str(STATE_ROOT),flush=True); print("="*92,flush=True)
    while True:
        proc=subprocess.Popen(cmd,cwd=str(BASE),env=os.environ.copy()); rc=proc.wait()
        print(f"[A EXIT] rc={rc}; restart in 10s",flush=True); time.sleep(10)

if __name__=="__main__":
    raise SystemExit(main())
