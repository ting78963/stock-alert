import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify
from group_limit_up import monitor_loop as group_limit_up_monitor_loop

app = Flask(__name__)
TPE = ZoneInfo("Asia/Taipei")
LINE_TOKEN = os.environ.get("LINE_TOKEN", "").strip()
GROUP_ID = os.environ.get("GROUP_ID", "").strip()

_group_limit_up_thread = None

def start_background_services():
    global _group_limit_up_thread
    if _group_limit_up_thread is None or not _group_limit_up_thread.is_alive():
        _group_limit_up_thread = threading.Thread(
            target=group_limit_up_monitor_loop,
            args=(LINE_TOKEN, GROUP_ID),
            name="group-limit-up-monitor",
            daemon=True,
        )
        _group_limit_up_thread.start()
        print("group limit-up notifier started", flush=True)

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

@app.get("/status")
def status():
    return jsonify(
        status="ok",
        taipei_time=datetime.now(TPE).isoformat(timespec="seconds"),
        fugle_key_configured=bool(os.environ.get("FUGLE_API_KEY", "").strip()),
        line_configured=bool(LINE_TOKEN and GROUP_ID),
        legacy_trading_strategy="removed",
        group_limit_up_notifier="enabled",
        b_engine="being_installed",
        scanner_a="blocked_until_fugle_snapshot_permission",
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
