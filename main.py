import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, request
from group_limit_up import monitor_loop as group_limit_up_monitor_loop, GROUPS_DISPLAY
from b_runner import monitor_loop as b_monitor_loop, discover as b_discover, status as b_status
from benchmark_3714 import run as run_3714_benchmark
from abc_buy_flex import abc_buy_flex, indicator_help_flex

app = Flask(__name__)
from fugle_web_proxy import bp as fugle_web_proxy_bp
app.register_blueprint(fugle_web_proxy_bp)
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

@app.post("/webhook")
def webhook():
    """LINE group text commands. Restores the legacy group-list command and
    adds the new indicator-help Flex card without touching trading logic."""
    body = request.get_json(silent=True)
    if not body:
        return "OK", 200
    for event in body.get("events", []):
        if event.get("type") != "message":
            continue
        message = event.get("message", {})
        if message.get("type") != "text":
            continue
        incoming = message.get("text", "")
        reply_token = event.get("replyToken", "")
        if not reply_token:
            continue

        reply_message = None
        if "指標說明" in incoming:
            reply_message = indicator_help_flex()
        elif "族群" in incoming:
            reply_message = {
                "type": "text",
                "text": "📊 族群清單：\nhttps://stock-alert-91j1.onrender.com/groups",
            }

        if reply_message is not None and LINE_TOKEN:
            try:
                r = requests.post(
                    "https://api.line.me/v2/bot/message/reply",
                    headers={
                        "Authorization": f"Bearer {LINE_TOKEN}",
                        "Content-Type": "application/json",
                    },
                    json={"replyToken": reply_token, "messages": [reply_message]},
                    timeout=10,
                )
                print(f"LINE webhook reply: {r.status_code}", flush=True)
            except Exception as e:
                print(f"LINE webhook reply error: {type(e).__name__}: {e}", flush=True)
    return "OK", 200

@app.get("/groups")
def groups_page():
    """Restored legacy group-list page, backed by the live notifier's list."""
    sections = {
        "半導體": ["IC設計","IC通路商","矽晶圓","成熟製程代工","半導體設備","先進封測","探針封測","ABF載板","記憶體"],
        "AI / 伺服器": ["AI伺服器","IPC邊緣AI","散熱","電源供應","BBU備援電池"],
        "通訊 / 衛星": ["光通訊","低軌衛星","連接線"],
        "被動 / 功率元件": ["被動元件","石英元件","功率元件","導線架"],
        "基板 / 材料": ["PCB高階","PCB玻纖布","玻璃基板"],
        "其他": ["機器人","廠務工程","重電","光學鏡頭","LED"],
    }
    html = """<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>族群清單｜台股漲停通知</title>
<style>*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,sans-serif;background:#f5f5f0;color:#1a1a1a;padding:16px}
h1{font-size:22px;font-weight:600;margin-bottom:4px}
p{font-size:13px;color:#888;margin-bottom:20px}
.st{font-size:11px;font-weight:600;color:#888;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px}
.g{background:#fff;border-radius:12px;padding:14px 16px;margin-bottom:8px;border:1px solid #ebebeb}
.gn{font-size:14px;font-weight:600;margin-bottom:10px;display:flex;justify-content:space-between}
.gc{font-size:11px;color:#aaa;background:#f5f5f0;padding:2px 8px;border-radius:20px}
.tags{display:flex;flex-wrap:wrap;gap:7px}
.tag{background:#f8f8f6;border:1px solid #e8e8e4;border-radius:8px;padding:7px 13px;font-size:14px}
.code{color:#e8192c;font-size:12px;margin-left:4px}</style></head><body>
<h1>🚀 族群清單</h1><p>台股漲停通知 @541etrau</p>"""
    for sec, group_names in sections.items():
        html += f'<div class="st" style="margin-bottom:10px">{sec}</div>'
        for group_name in group_names:
            if group_name in GROUPS_DISPLAY:
                stocks = GROUPS_DISPLAY[group_name]
                html += f'<div class="g"><div class="gn">{group_name}<span class="gc">{len(stocks)}支</span></div><div class="tags">'
                for stock_name, code in stocks:
                    html += f'<span class="tag">{stock_name}<span class="code">{code}</span></span>'
                html += '</div></div>'
    html += '</body></html>'
    return html


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


@app.get("/audit/indicator-help-flex-4d82")
def audit_indicator_help_flex():
    """Temporary fixed visual-only LINE test for 指標說明."""
    if not LINE_TOKEN or not GROUP_ID:
        return jsonify(ok=False,error="LINE_NOT_CONFIGURED"),500
    msg=indicator_help_flex()
    try:
        r=requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization":f"Bearer {LINE_TOKEN}","Content-Type":"application/json"},
            json={"to":GROUP_ID,"messages":[msg]},timeout=10,
        )
        return jsonify(ok=200<=r.status_code<300,line_status=r.status_code,
                       test_only=True,card="indicator_help"), (200 if 200<=r.status_code<300 else 502)
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
