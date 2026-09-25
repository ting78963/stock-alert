import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify
from group_limit_up import monitor_loop as group_limit_up_monitor_loop
from b_runner import monitor_loop as b_monitor_loop, discover as b_discover, status as b_status
from benchmark_3714 import run as run_3714_benchmark
from abc_buy_flex import abc_buy_flex

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

@app.get("/audit/2369-live")
def audit_2369_live():
    """Fixed one-stock production replay for today's agreed 2369 handoff.

    Uses the exact production B evaluator and the fixed 10:38 discovery time.
    This endpoint accepts no user-selected symbol/time, so it cannot become an
    unprotected general production control surface. A genuine production
    A/B/C+Early result may send the real LINE notification, exactly as B does.
    """
    import b_runner
    sid="2369"
    meta={"discovered_at":"10:38:00","name":None}
    try:
        b_runner._evaluate(sid,meta,LINE_TOKEN,GROUP_ID)
        return jsonify(ok=True,stock_id=sid,discovered_at="10:38:00",
                       engine="production_B",status=b_status())
    except Exception as e:
        return jsonify(ok=False,stock_id=sid,error=type(e).__name__,detail=str(e)),500

@app.get("/audit/2369-attack-trace")
def audit_2369_attack_trace():
    """Fixed read-only 2369 Attack audit through 11:10; no LINE/state mutation."""
    import b_runner
    try:
        result=b_runner.attack_trace("2369",{"discovered_at":"11:10:00","name":None})
        # Keep only decisive Attack transitions plus the key/A2 summary.
        result["trace"]=[x for x in result.get("trace",[]) if x.get("event")]
        return jsonify(ok=True,result=result)
    except Exception as e:
        return jsonify(ok=False,stock_id="2369",error=type(e).__name__,detail=str(e)),500

@app.get("/internal/b-evaluate/<symbol>")
def internal_b_evaluate(symbol):
    # Diagnostic production evaluation for an already-discovered symbol.
    # Uses the exact same B evaluation path; does not alter signal semantics.
    from flask import request
    expected=os.environ.get("ABC_DISCOVERY_TOKEN","").strip()
    if not expected or request.headers.get("X-ABC-Token","") != expected:
        return jsonify(ok=False,error="unauthorized"),403
    sid=str(symbol).zfill(4)
    with __import__("b_runner")._lock:
        meta=__import__("b_runner")._watch.get(sid)
    if not meta:
        return jsonify(ok=False,error="not_watching",stock_id=sid),404
    try:
        __import__("b_runner")._evaluate(sid,meta,LINE_TOKEN,GROUP_ID)
        return jsonify(ok=True,stock_id=sid,status=b_status())
    except Exception as e:
        return jsonify(ok=False,stock_id=sid,error=type(e).__name__,detail=str(e)),500


@app.get("/internal/b-attack-trace/<symbol>")
def internal_b_attack_trace(symbol):
    # Protected, read-only causal trace. Never sends LINE and never mutates signal state.
    from flask import request
    import b_runner
    expected=os.environ.get("ABC_DISCOVERY_TOKEN","").strip()
    if not expected or request.headers.get("X-ABC-Token","") != expected:
        return jsonify(ok=False,error="unauthorized"),403
    sid=str(symbol).zfill(4)
    with b_runner._lock:
        meta=b_runner._watch.get(sid)
    if not meta:
        return jsonify(ok=False,error="not_watching",stock_id=sid),404
    try:
        return jsonify(ok=True,result=b_runner.attack_trace(sid,meta))
    except Exception as e:
        return jsonify(ok=False,stock_id=sid,error=type(e).__name__,detail=str(e)),500

@app.get("/audit/p1-flex-6207-9f2c7a")
def audit_p1_flex_6207():
    """Temporary fixed visual-only LINE Flex test. No recognition/state mutation."""
    if not LINE_TOKEN or not GROUP_ID:
        return jsonify(ok=False,error="LINE_NOT_CONFIGURED"),500
    event={
        "stock_id":"6207","stock_name":"雷科","signal_class":"P1",
        "recognition_time":"09:28:00","live_known_time":"09:28:00",
    }
    msg=abc_buy_flex(event,"雷科")
    try:
        r=requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization":f"Bearer {LINE_TOKEN}","Content-Type":"application/json"},
            json={"to":GROUP_ID,"messages":[msg]},timeout=10,
        )
        return jsonify(ok=200<=r.status_code<300,line_status=r.status_code,
                       test_only=True,stock_id="6207",name="雷科"), (200 if 200<=r.status_code<300 else 502)
    except Exception as e:
        return jsonify(ok=False,error=type(e).__name__,detail=str(e)),500

@app.get("/audit/flex-preview-all")
def audit_flex_preview_all():
    """Fixed visual-only preview payload for P1/A/B/C. Never sends LINE."""
    samples=[
        ("6207","雷科","P1","09:28:00"),
        ("3714","富采","A","10:28:00"),
        ("3665","貿聯-KY","B","10:02:00"),
        ("3231","緯創","C","09:45:00"),
    ]
    cards=[]
    for sid,name,cls,t in samples:
        event={"stock_id":sid,"stock_name":name,"signal_class":cls,
               "recognition_time":t,"live_known_time":t}
        cards.append(abc_buy_flex(event,name))
    return jsonify(ok=True,test_only=True,cards=cards)

@app.get("/audit/flex-send-all-7c31")
def audit_flex_send_all():
    """Temporary fixed visual-only LINE test for P1/A/B/C. No recognition/state mutation."""
    if not LINE_TOKEN or not GROUP_ID:
        return jsonify(ok=False,error="LINE_NOT_CONFIGURED"),500
    samples=[
        ("6207","雷科","P1","09:28:00"),
        ("3714","富采","A","10:28:00"),
        ("3665","貿聯-KY","B","10:02:00"),
        ("3231","緯創","C","09:45:00"),
    ]
    messages=[]
    for sid,name,cls,t in samples:
        event={"stock_id":sid,"stock_name":name,"signal_class":cls,
               "recognition_time":t,"live_known_time":t}
        messages.append(abc_buy_flex(event,name))
    try:
        r=requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization":f"Bearer {LINE_TOKEN}","Content-Type":"application/json"},
            json={"to":GROUP_ID,"messages":messages},timeout=10,
        )
        return jsonify(ok=200<=r.status_code<300,line_status=r.status_code,
                       test_only=True,cards=["P1","A","B","C"]), (200 if 200<=r.status_code<300 else 502)
    except Exception as e:
        return jsonify(ok=False,error=type(e).__name__,detail=str(e)),500

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
