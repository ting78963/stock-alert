import os
import time
import math
import json
import base64
import requests
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, request

app = Flask(__name__)

LINE_TOKEN = os.environ.get("LINE_TOKEN", "")
GROUP_ID = os.environ.get("GROUP_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ===== 訊號參數 =====
FIRST_MULT = 1.25        # 第一次⚡觸發倍數
SECOND_MULT_A = round(math.sqrt(1.25), 3)  # 🔥(A) 無警示，×1.118
WARNING_RATIO = 0.8      # ⚠️警示門檻
TRACK_MIN_PCT = 3.0      # 族群系統追蹤起始%
GOLD_MIN_PCT = 4.0       # 黃金奇點追蹤起始%
GOLD_PRICE_MIN = 101     # 黃金奇點最低股價
GOLD_PRICE_MAX = 130     # 黃金奇點最高股價
SIGNAL_CUTOFF_HOUR = 12  # 12:00後不發⚡訊號

TZ = timezone(timedelta(hours=8))

# ===== 族群清單 =====
GROUPS = {
    "IC設計": ["3661","3443","3035","2388","8040","4966","3209","2363","2401","6415"],
    "IC通路商": ["3034","2379"],
    "矽晶圓": ["6488","3532","6182","3016","5483","3707","4934","8028","1560","3583","3374"],
    "成熟製程代工": ["2303","5347","6770"],
    "半導體設備": ["3583","3131","6187","8028","1560","2467","6664","5443","3030","3563","3535","3455","3680","7769","3485","8027","8064","6640","6207"],
    "先進封測": ["3711","6239","6257","6147","8150","2449","3265","8016","2329"],
    "探針封測": ["6515","6223","6510","6217"],
    "ABF載板": ["3037","8046","3189","4958"],
    "記憶體": ["2408","2344","6531","3260","8112","2337","3006","5351","8299","5289","6770","5386","8096","3135","8271","2451","4967"],
    "IPC邊緣AI": ["2395","2376","2377","6414","2357","3088","6166","6245","3577","6579","3594","2356","2353","4938","3213"],
    "AI伺服器": ["2317","6669","3231","2382"],
    "散熱": ["3017","3324","3653","8996","3013","2421","6805","2486"],
    "光通訊": ["3081","3363","3163","6442","6451","4977","4979","3450","2455","4971","4991","3234","6530","4903","4906","4908","6588","8086","6278","3071","2402","2489","3105"],
    "低軌衛星": ["2313","3491","6285","2367","3105","2485","3138","8086","4909","6443","2464","6271","2355","4912","1582","4916"],
    "被動元件": ["2327","2492","2375","3026","6449","6284","3236","3357","2478","3624","3090","6173","2472","6862","8163","6127","6834","8042","6155","3537","6175","8043","8121"],
    "石英元件": ["3042","2484","3221","8182","6174","8289"],
    "功率元件": ["2481","3675","5425","8255","6138","8261"],
    "機器人": ["2049","1597","2464","8374","7750","4576","4526","2328","2233","4562","2359","2374","6215","4951","1536"],
    "廠務工程": ["2404","6139","5536","6196","6944","4768","7820","3402","8091","6725"],
    "重電": ["1519","1513","1503","1514"],
    "PCB高階": ["8021","5498","8074","8358","4089","3645"],
    "PCB玻纖布": ["5475","1815","1802","1303","5340"],
    "光學鏡頭": ["3008","3362","3406","2498","3019","3504","6209","3441","6668"],
    "玻璃基板": ["3481","8064","3580","3149","8027","6207","3055"],
    "LED": ["6706","6456","6226","2426","4956","3714","3437","3339","6168","8215","6854","6789"],
    "連接線": ["3533","3665","6197","6715","3526","3605","3023"],
    "電源供應": ["2308","2301","6282","6412"],
    "導線架": ["2351","6548","5285","8070","2483"],
    "BBU備援電池": ["6781","3211","4931","5309","6558","3323"],
}

STOCK_TO_GROUP = {}
for g, stocks in GROUPS.items():
    for s in stocks:
        if s not in STOCK_TO_GROUP:
            STOCK_TO_GROUP[s] = g

# ===== 狀態變數 =====
notified = set()          # 已發漲停通知的股票
triggered_groups = set()  # 今天已有漲停的族群

# tracking結構：{code: {name, group, source, start_pct, trigger_count,
#   first_trigger_pct, had_warning, warning_active, warning_low_pct}}
tracking = {}

# 黃金奇點清單：{code: {name, prev_close}}
gold_list = {}

# 每日記錄（收盤統計用）
daily_records = []
closing_done_date = None

def is_trading_time():
    now = datetime.now(TZ)
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 13 * 60 + 30

def is_signal_time():
    """12:00前才發⚡訊號"""
    now = datetime.now(TZ)
    return now.hour < SIGNAL_CUTOFF_HOUR

def get_now_str():
    return datetime.now(TZ).strftime("%H:%M:%S")

def fetch_stock_data(codes):
    """抓指定股票清單的即時資料"""
    results = {}
    batch_size = 25
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        ex_ch = "|".join([f"tse_{s}.tw|otc_{s}.tw" for s in batch])
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0"
        try:
            res = requests.get(url, timeout=10)
            data = res.json()
            for item in data.get("msgArray", []):
                code = item.get("c", "")
                name = item.get("n", "")
                z = item.get("z", "-")
                y = item.get("y", "-")
                if code and z not in ["-",""] and y not in ["-",""] and float(y) > 0:
                    pct = (float(z) - float(y)) / float(y) * 100
                    results[code] = {
                        "name": name,
                        "change_pct": round(pct, 2),
                        "price": float(z),
                        "prev_close": float(y),
                        "is_limit_up": pct >= 9.5
                    }
        except Exception as e:
            print(f"API錯誤: {e}", flush=True)
        time.sleep(0.2)
    return results

def fetch_all_market_prev_close():
    """每天開盤前抓全市場昨收價，建立黃金奇點清單"""
    global gold_list
    all_codes = []
    # 從族群清單取得所有代號
    group_codes = set([s for stocks in GROUPS.values() for s in stocks])
    # 抓所有族群股票的昨收
    results = fetch_stock_data(list(group_codes))
    new_gold = {}
    for code, info in results.items():
        if GOLD_PRICE_MIN <= info["prev_close"] <= GOLD_PRICE_MAX:
            new_gold[code] = {"name": info["name"], "prev_close": info["prev_close"]}
    gold_list = new_gold
    print(f"黃金奇點清單更新：{len(gold_list)}隻（{GOLD_PRICE_MIN}~{GOLD_PRICE_MAX}元）", flush=True)

def send_line_message(msg):
    if not GROUP_ID or not LINE_TOKEN:
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    data = {"to": GROUP_ID, "messages": [{"type": "text", "text": msg}]}
    try:
        res = requests.post(url, headers=headers, json=data)
        print(f"LINE: {res.status_code}", flush=True)
    except Exception as e:
        print(f"LINE錯誤: {e}", flush=True)

def record_signal(group, code, name, pct, category):
    daily_records.append({
        "group": group, "code": code, "name": name,
        "signal_pct": round(pct, 1), "category": category,
        "time": get_now_str()
    })

def push_to_github(filename, content_dict):
    if not GITHUB_TOKEN:
        return
    repo = "ting78963/stock"
    api_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    sha = None
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code == 200:
            sha = res.json().get("sha")
    except:
        pass
    content_b64 = base64.b64encode(json.dumps(content_dict, ensure_ascii=False, indent=2).encode()).decode()
    data = {"message": f"Update {filename}", "content": content_b64}
    if sha:
        data["sha"] = sha
    try:
        res = requests.put(api_url, headers=headers, json=data, timeout=15)
        print(f"GitHub push: {res.status_code}", flush=True)
    except Exception as e:
        print(f"GitHub push錯誤: {e}", flush=True)

def process_tracking_signals(stock_data):
    """處理所有tracking中的股票，收集訊號"""
    # 收集各類訊號
    signals = {"⚡": [], "🔥": [], "⚠️": [], "❌": []}
    now_str = get_now_str()
    can_signal = is_signal_time()

    for code, track in list(tracking.items()):
        if code not in stock_data:
            continue
        current_pct = stock_data[code]["change_pct"]
        name = stock_data[code]["name"] or track["name"] or code
        group = track["group"]
        source = track.get("source", "族群")

        first_pct = track["first_trigger_pct"]
        warn_threshold = round(first_pct * WARNING_RATIO, 2) if first_pct else None
        trigger_count = track["trigger_count"]
        had_warning = track["had_warning"]
        warning_active = track["warning_active"]
        warning_low = track["warning_low_pct"]

        if trigger_count == 0:
            # 等待第一次⚡
            threshold = round(track["start_pct"] * FIRST_MULT, 2)
            if current_pct >= threshold and can_signal:
                tracking[code]["trigger_count"] = 1
                tracking[code]["first_trigger_pct"] = current_pct
                tracking[code]["warning_active"] = False
                signals["⚡"].append({
                    "code": code, "name": name, "group": group, "source": source,
                    "from_pct": track["start_pct"], "to_pct": current_pct
                })
                record_signal(group, code, name, current_pct,
                    "above_4" if current_pct >= 4.0 else "above_3")

        elif trigger_count == 1:
            # 已有⚡，等待🔥或⚠️
            if not warning_active:
                if not had_warning:
                    # 情況A：看×1.118
                    fire_threshold = min(round(first_pct * SECOND_MULT_A, 2), 9.5)
                    if current_pct >= fire_threshold and can_signal:
                        tracking[code]["trigger_count"] = 2
                        signals["🔥"].append({
                            "code": code, "name": name, "group": group, "source": source,
                            "from_pct": first_pct, "to_pct": current_pct, "type": "A"
                        })
                    elif current_pct <= warn_threshold:
                        tracking[code]["warning_active"] = True
                        tracking[code]["had_warning"] = True
                        tracking[code]["warning_low_pct"] = current_pct
                        signals["⚠️"].append({
                            "code": code, "name": name, "group": group, "source": source,
                            "from_pct": first_pct, "to_pct": current_pct
                        })
                else:
                    # 情況B：等回到觸發點
                    if current_pct >= first_pct and can_signal:
                        tracking[code]["trigger_count"] = 2
                        tracking[code]["warning_active"] = False
                        signals["🔥"].append({
                            "code": code, "name": name, "group": group, "source": source,
                            "from_pct": warning_low or first_pct, "to_pct": current_pct, "type": "B"
                        })
                    elif current_pct <= warn_threshold:
                        # 再次跌破警示門檻
                        if warning_low and current_pct < warning_low:
                            tracking[code]["warning_low_pct"] = current_pct
                        signals["⚠️"].append({
                            "code": code, "name": name, "group": group, "source": source,
                            "from_pct": first_pct, "to_pct": current_pct
                        })
            else:
                # 警示中，追蹤反彈
                if warning_low and current_pct < warning_low:
                    tracking[code]["warning_low_pct"] = current_pct
                # 回到觸發點 → 🔥(B)
                if current_pct >= first_pct and can_signal:
                    tracking[code]["trigger_count"] = 2
                    tracking[code]["warning_active"] = False
                    signals["🔥"].append({
                        "code": code, "name": name, "group": group, "source": source,
                        "from_pct": tracking[code]["warning_low_pct"] or first_pct,
                        "to_pct": current_pct, "type": "B"
                    })
                # 再次跌破 → ❌
                elif current_pct <= warn_threshold and track["had_warning"]:
                    del tracking[code]
                    signals["❌"].append({
                        "code": code, "name": name, "group": group, "source": source,
                        "pct": current_pct
                    })
                    continue

        elif trigger_count == 2:
            # 已有🔥，繼續監控
            warn2 = round(first_pct * WARNING_RATIO, 2)
            if current_pct <= warn2:
                signals["⚠️"].append({
                    "code": code, "name": name, "group": group, "source": source,
                    "from_pct": first_pct, "to_pct": current_pct
                })

    return signals

def build_signal_message(signals):
    """把所有訊號合併成一則訊息"""
    now_str = get_now_str()
    lines = [f"📊 訊號更新｜{now_str}"]

    order = ["🔥", "⚡", "⚠️", "❌"]
    names = {"🔥": "確認突破", "⚡": "急拉訊號", "⚠️": "回落警示", "❌": "突破失敗"}
    has_content = False

    for emoji in order:
        items = signals.get(emoji, [])
        if not items:
            continue
        has_content = True
        lines.append("━━━━━━━━━━━━━━━━")
        lines.append(f"{emoji} {names[emoji]}")
        for item in items:
            source_tag = "｜黃金奇點" if item.get("source") == "黃金奇點" else f"｜{item['group']}"
            if emoji == "❌":
                lines.append(f"{item['name']} {item['code']}{source_tag}　{item['pct']:+.2f}%")
            else:
                fire_type = ""
                if emoji == "🔥":
                    fire_type = "⚠️考驗" if item.get("type") == "B" else ""
                lines.append(f"{item['name']} {item['code']}{source_tag}　{item['from_pct']:+.1f}%→{item['to_pct']:+.1f}% {fire_type}")

    if not has_content:
        return None

    return "\n".join(lines)

def add_to_tracking(code, name, group, start_pct, source="族群"):
    """加入追蹤清單"""
    if code not in tracking:
        tracking[code] = {
            "name": name, "group": group, "source": source,
            "start_pct": start_pct,
            "trigger_count": 0,
            "first_trigger_pct": None,
            "had_warning": False,
            "warning_active": False,
            "warning_low_pct": None,
        }

def check_stocks():
    now = datetime.now(TZ)
    print(f"監控中 台灣時間：{now.strftime('%H:%M:%S')} 交易時間：{is_trading_time()}", flush=True)

    if not is_trading_time():
        notified.clear()
        tracking.clear()
        triggered_groups.clear()
        return

    # 取得所有需要監控的股票
    all_codes = list(set([s for stocks in GROUPS.values() for s in stocks]))
    gold_codes = list(gold_list.keys())
    all_codes_to_fetch = list(set(all_codes + gold_codes + list(tracking.keys())))

    stock_data = fetch_stock_data(all_codes_to_fetch)

    # ===== 1. 處理tracking訊號 =====
    signals = process_tracking_signals(stock_data)
    msg = build_signal_message(signals)
    if msg:
        send_line_message(msg)
        print(msg, flush=True)

    # ===== 2. 偵測族群漲停 =====
    for code, info in stock_data.items():
        if code in notified or not info["is_limit_up"]:
            continue
        group = STOCK_TO_GROUP.get(code, "")
        if not group:
            continue

        notified.add(code)
        triggered_groups.add(group)
        name = info["name"] or code

        # 族群其他股票
        high = []
        mid = []
        for other_code in GROUPS.get(group, []):
            if other_code == code or other_code not in stock_data:
                continue
            other_info = stock_data[other_code]
            other_pct = other_info["change_pct"]
            other_name = other_info["name"] or other_code

            # 加入追蹤
            if other_pct >= TRACK_MIN_PCT:
                add_to_tracking(other_code, other_name, group, other_pct, "族群")

            if other_pct >= 4.0:
                high.append(f"{other_name} {other_code}　{other_pct:+.1f}%")
                record_signal(group, other_code, other_name, other_pct, "above_4")
            elif other_pct >= 3.0:
                mid.append(f"{other_name} {other_code}　{other_pct:+.1f}%")
                record_signal(group, other_code, other_name, other_pct, "above_3")

        # 發漲停通知
        now_str = now.strftime("%H:%M:%S")
        msg = f"🚀 漲停通知｜{group}\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"{name} {code}　{info['change_pct']:+.1f}% 🔴 漲停\n"
        msg += f"時間：{now_str}\n"
        if high:
            msg += f"\n同族群 4%以上：\n" + "\n".join(high)
        if mid:
            msg += f"\n\n同族群 3~4%：\n" + "\n".join(mid)
        send_line_message(msg)
        print(msg, flush=True)

    # ===== 3. 已觸發族群，持續追蹤新進入3%的股票 =====
    for group in triggered_groups:
        for code in GROUPS.get(group, []):
            if code in notified or code in tracking or code not in stock_data:
                continue
            pct = stock_data[code]["change_pct"]
            if pct >= TRACK_MIN_PCT:
                name = stock_data[code]["name"] or code
                add_to_tracking(code, name, group, pct, "族群")

    # ===== 4. 黃金奇點掃描 =====
    for code, gold_info in gold_list.items():
        if code in tracking or code not in stock_data:
            continue
        pct = stock_data[code]["change_pct"]
        if pct >= GOLD_MIN_PCT:
            name = stock_data[code]["name"] or gold_info["name"] or code
            add_to_tracking(code, name, "黃金奇點", pct, "黃金奇點")

def do_closing_summary():
    """收盤統計"""
    if not daily_records:
        print("今天沒有記錄", flush=True)
        return

    codes = list(set([r["code"] for r in daily_records]))
    final_data = {}
    for i in range(0, len(codes), 25):
        batch = codes[i:i+25]
        ex_ch = "|".join([f"tse_{s}.tw|otc_{s}.tw" for s in batch])
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0"
        try:
            res = requests.get(url, timeout=10)
            for item in res.json().get("msgArray", []):
                code = item.get("c", "")
                h = item.get("h", "-")
                z = item.get("z", "-")
                y = item.get("y", "-")
                if code and h not in ["-",""] and y not in ["-",""] and float(y) > 0:
                    high_pct = (float(h) - float(y)) / float(y) * 100
                    close_pct = (float(z) - float(y)) / float(y) * 100 if z not in ["-",""] else None
                    final_data[code] = {
                        "high_pct": round(high_pct, 1),
                        "close_pct": round(close_pct, 1) if close_pct else None
                    }
        except Exception as e:
            print(f"收盤查詢錯誤: {e}", flush=True)
        time.sleep(0.2)

    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    today_records = []
    for r in daily_records:
        final = final_data.get(r["code"], {})
        high_pct = final.get("high_pct")
        close_pct = final.get("close_pct")
        signal_pct = r["signal_pct"]
        today_records.append({
            **r,
            "high_pct": high_pct,
            "close_pct": close_pct,
            "final_limit_up": (high_pct is not None and high_pct >= 9.5),
            "exceeded_signal_pct": (high_pct is not None and high_pct > signal_pct)
        })

    # 讀取歷史+合併+push
    history = {}
    try:
        res = requests.get("https://raw.githubusercontent.com/ting78963/stock/main/stats.json", timeout=10)
        if res.status_code == 200:
            history = res.json()
    except:
        pass
    history[today_str] = today_records
    push_to_github("stats.json", history)

    # 發LINE收盤統計
    above4 = [r for r in today_records if r["category"] == "above_4"]
    above3 = [r for r in today_records if r["category"] == "above_3"]
    above4_win = [r for r in above4 if r["exceeded_signal_pct"]]
    above3_win = [r for r in above3 if r["exceeded_signal_pct"]]

    msg = f"📊 今日收盤統計｜{today_str}\n"
    msg += "━━━━━━━━━━━━━━━━\n"
    if above4:
        msg += f"\n4%以上（{len(above4)}筆，勝率{len(above4_win)}/{len(above4)}）：\n"
        for r in above4:
            win = "✅" if r["exceeded_signal_pct"] else "❌"
            high = f"+{r['high_pct']}%" if r["high_pct"] else "?"
            msg += f"{win} {r['name']} {r['code']}　通知{r['signal_pct']:+.1f}% → 最高{high}\n"
    if above3:
        msg += f"\n3~4%（{len(above3)}筆，勝率{len(above3_win)}/{len(above3)}）：\n"
        for r in above3:
            win = "✅" if r["exceeded_signal_pct"] else "❌"
            high = f"+{r['high_pct']}%" if r["high_pct"] else "?"
            msg += f"{win} {r['name']} {r['code']}　通知{r['signal_pct']:+.1f}% → 最高{high}\n"
    if not above4 and not above3:
        msg += "今日無訊號記錄"

    send_line_message(msg)
    print(f"收盤統計完成，共{len(today_records)}筆", flush=True)
    daily_records.clear()

def check_closing_time():
    global closing_done_date
    now = datetime.now(TZ)
    today_str = now.strftime("%Y-%m-%d")
    t = now.hour * 60 + now.minute
    if 13*60+30 <= t <= 13*60+35 and closing_done_date != today_str and now.weekday() < 5:
        do_closing_summary()
        closing_done_date = today_str

def check_gold_list_update():
    """每天08:55更新黃金奇點清單"""
    now = datetime.now(TZ)
    t = now.hour * 60 + now.minute
    if t == 8*60+55 and now.weekday() < 5:
        fetch_all_market_prev_close()

# ===== Flask路由 =====
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    if not body:
        return "OK", 200
    for event in body.get("events", []):
        if event.get("type") == "message":
            text = event.get("message", {}).get("text", "")
            reply_token = event.get("replyToken", "")
            if "族群" in text and reply_token:
                reply_msg = "📊 族群清單：\nhttps://stock-alert-91j1.onrender.com/groups"
                requests.post(
                    "https://api.line.me/v2/bot/message/reply",
                    headers={"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"},
                    json={"replyToken": reply_token, "messages": [{"type": "text", "text": reply_msg}]}
                )
    return "OK", 200

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/test")
def test():
    msg = "🚀 漲停通知｜散熱\n━━━━━━━━━━━━━━━━\n奇鋐 3017　+10.0% 🔴 漲停\n時間：10:23:45\n\n同族群 4%以上：\n雙鴻 3324　+6.2%\n\n同族群 3~4%：\n高力 8996　+3.8%\n\n⚠️ 此為系統測試訊息"
    send_line_message(msg)
    return "已發送！", 200

@app.route("/gold")
def gold():
    return f"黃金奇點清單：{len(gold_list)}隻<br>" + "<br>".join([f"{c} {v['name']} 昨收{v['prev_close']}" for c, v in list(gold_list.items())[:20]]), 200

@app.route("/groups")
def groups_page():
    html = """<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>族群清單</title>
<style>*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,sans-serif;background:#f5f5f0;padding:16px}
h1{font-size:22px;margin-bottom:16px}
.group{background:#fff;border-radius:12px;padding:14px;margin-bottom:8px;border:1px solid #ebebeb}
.gname{font-size:14px;font-weight:600;margin-bottom:10px}
.tags{display:flex;flex-wrap:wrap;gap:6px}
.tag{background:#f8f8f6;border:1px solid #e8e8e4;border-radius:8px;padding:6px 12px;font-size:13px}
.code{color:#e8192c;font-size:11px;margin-left:3px}</style></head>
<body><h1>🚀 族群清單｜@541etrau</h1>"""
    GROUPS_DISPLAY = {
        "散熱": [("奇鋐","3017"),("雙鴻","3324"),("健策","3653"),("高力","8996"),("建準","2421"),("富世達","6805")],
        "機器人": [("上銀","2049"),("直得","1597"),("盟立","2464"),("羅昇","8374"),("東元","4526")],
        "光通訊": [("聯亞","3081"),("上詮","3363"),("華星光","4979"),("聯鈞","3450"),("環宇-KY","4991"),("正文","4906"),("瑞軒","2489")],
        "被動元件": [("國巨","2327"),("華新科","2492"),("大毅","2478"),("光頡","3624"),("信昌電","6173")],
        "記憶體": [("南亞科","2408"),("華邦電","2344"),("旺宏","2337"),("群聯","8299"),("宇瞻","8271"),("宜鼎","5289")],
    }
    for gname, stocks in GROUPS_DISPLAY.items():
        html += f'<div class="group"><div class="gname">{gname}</div><div class="tags">'
        for sname, code in stocks:
            html += f'<span class="tag">{sname}<span class="code">{code}</span></span>'
        html += '</div></div>'
    html += '</body></html>'
    return html

def monitor_loop():
    while True:
        try:
            check_gold_list_update()
            check_stocks()
            check_closing_time()
        except Exception as e:
            print(f"監控錯誤: {e}", flush=True)
        time.sleep(5)

monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
