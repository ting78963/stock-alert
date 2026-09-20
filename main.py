import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify
from group_limit_up import monitor_loop as group_limit_up_monitor_loop
from b_runner import monitor_loop as b_monitor_loop, discover as b_discover, status as b_status
from benchmark_3714 import run as run_3714_benchmark

app = Flask(__name__)
TPE = ZoneInfo("Asia/Taipei")
LINE_TOKEN = os.environ.get("LINE_TOKEN", "").strip()
GROUP_ID = os.environ.get("GROUP_ID", "").strip()

_group_limit_up_thread = None
_b_thread = None

def start_background_services():
    global _group_limit_up_thread, _b_thread
    if _group_limit_up_thread is None or not _group_limit_up_thread.is_alive():
        _group_limit_up_thread = threading.Thread(
            target=group_limit_up_monitor_loop,
            args=(LINE_TOKEN, GROUP_ID),
            name="group-limit-up-monitor",
            daemon=True,
        )
        _group_limit_up_thread.start()
        print("group limit-up notifier started", flush=True)
    if _b_thread is None or not _b_thread.is_alive():
        _b_thread = threading.Thread(
            target=b_monitor_loop,
            args=(LINE_TOKEN, GROUP_ID),
            name="abc-b-runner",
            daemon=True,
        )
        _b_thread.start()
        print("ABC B runner started", flush=True)

start_background_services()

def send_line(msg: str) -> bool:
    if not LINE_TOKEN or not GROUP_ID:
        print("[LINE DISABLED] missing LINE_TOKEN/GROUP_ID", flush=True)
        return False
    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"},
        json={"to": GROUP_ID, "messages": [{"type": "text", "text": msg}]},
        timeout=10,
    )
    print(f"LINE: {r.status_code}", flush=True)
    return 200 <= r.status_code < 300

@app.get("/")
def root():
    return jsonify(service="stock-alert", system="Fugle A/B/C production", status="ok")

@app.get("/ping")
def ping():
    return "pong", 200


@app.post("/internal/discover/<symbol>")
def internal_discover(symbol):
    # Temporary A->B handoff endpoint. Protected by ABC_DISCOVERY_TOKEN.
    from flask import request
    expected=os.environ.get("ABC_DISCOVERY_TOKEN","").strip()
    if not expected or request.headers.get("X-ABC-Token","") != expected:
        return jsonify(ok=False,error="unauthorized"),403
    body=request.get_json(silent=True) or {}
    at=body.get("discovered_at") or datetime.now(TPE).strftime("%H:%M:%S")
    added=b_discover(symbol,at,body.get("name"))
    return jsonify(ok=True,added=added,stock_id=str(symbol).zfill(4),discovered_at=at)

@app.get("/audit/3714")
def audit_3714():
    try:
        result=run_3714_benchmark()
        code=200 if result.get("audit")=="PASS" else 409
        return jsonify(result),code
    except Exception as e:
        return jsonify(audit="AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL",
                       line_sent=False,error=type(e).__name__,detail=str(e)),500

@app.get("/status")
def status():
    return jsonify(
        status="ok",
        taipei_time=datetime.now(TPE).isoformat(timespec="seconds"),
        fugle_key_configured=bool(os.environ.get("FUGLE_API_KEY", "").strip()),
        line_configured=bool(LINE_TOKEN and GROUP_ID),
        legacy_trading_strategy="removed",
        group_limit_up_notifier="enabled",
        b_engine=b_status(),
        scanner_a="blocked_until_fugle_snapshot_permission",
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
