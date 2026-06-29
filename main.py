import os
import time
import requests
import threading
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)

# ===== 設定區 =====
LINE_TOKEN = os.environ.get("LINE_TOKEN", "")
GROUP_ID = os.environ.get("GROUP_ID", "")

# ===== 族群股票清單 =====
GROUPS = {
    "IC設計｜客製ASIC與矽智財": ["3661","3443","3035","6643","3529"],
    "半導體製造｜矽晶圓": ["6488","5483","3532","6182"],
    "半導體製造｜晶圓代工": ["2303","5347","6770","3707"],
    "半導體製造｜晶圓廠設備": ["3583","3680","3413","3131","8028"],
    "半導體製造｜前段製程材料": ["1560","4749","4772","1727","3663"],
    "半導體製造｜第三代半導體": ["3016","2455","6266","8086","2342"],
    "先進封測｜ABF載板CoWoS": ["3037","8046","3189","4958","3374","2383"],
    "先進封測｜封測代工OSAT": ["3711","6239","6257","6147","8150"],
    "先進封測｜IC測試服務": ["2449","6515","6510","6223","6217"],
    "記憶體｜HBM高頻寬記憶體": ["2408","2344","6531","3260","8112"],
    "記憶體｜NOR Flash與利基記憶體": ["2337","3006","5351","8299"],
    "記憶體｜CXL記憶體池化": ["5274","5269","4966","6104","5289"],
    "AI伺服器｜整機組裝": ["6669","2382","2356","2376","2377"],
    "AI伺服器｜高速連接器": ["3533"],
    "散熱冷卻｜氣冷與核心組件": ["3017","3324","3653","3689","6275"],
    "散熱冷卻｜液冷散熱系統": ["8996","3013","2421","6125","3483"],
    "光通訊｜高速光收發模組": ["3081","3363","3163","6715","6442"],
    "光通訊｜矽光子與CPO": ["6451","6789","4977","4979","3450"],
    "衛星通訊｜低軌衛星通訊系統": ["2313","3491","6285","2314","2367","3105"],
    "網路設備｜高速交換器與無線網路": ["2345","2379","5388","3380","6526"],
    "基板材料｜玻纖布": ["6213","6274","1815","5340"],
    "基板材料｜玻璃基板": ["1802","6207","3615","2467","3149","3481"],
    "被動元件｜電容器": ["2327","2492","2375","3026","6449","6271"],
    "被動元件｜功率電感": ["2456","6284","2351","3236","3357"],
    "被動元件｜電阻": ["2478","2428","3624","6224"],
    "被動元件｜石英頻率控制": ["3042","2484","3221","6282"],
    "功率元件｜矽基功率離散元件": ["2481","3675","5425","8255","6138","8261"],
    "智慧機器人｜實體AI機器人": ["2049","1597","4540","4585","4583"],
    "智慧機器人｜工業自動化": ["2395","1590","6414","8374","6166","2464"],
    "智慧機器人｜Edge AI/AIoT": ["3022","3454","5484","6579","8234"],
    "廠務工程｜EPC工程服務": ["2404","6139","5536","6196","3402"],
    "重電｜電器電纜與重電": ["1519","1513","1503","2371","1605"],
    "光學顯示｜光學鏡頭": ["3008","3406","3362","6209","3504"],
}

# 股號反查族群
STOCK_TO_GROUP = {}
for group_name, stocks in GROUPS.items():
    for stock in stocks:
        STOCK_TO_GROUP[stock] = group_name

# 已通知記錄
notified = set()
last_reset_date = datetime.now().date()

def reset_daily():
    global notified, last_reset_date
    today = datetime.now().date()
    if today != last_reset_date:
        notified.clear()
        last_reset_date = today

def is_trading_time():
    from datetime import timezone, timedelta
    tz_taipei = timezone(timedelta(hours=8))
    now = datetime.now(tz_taipei)
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 13 * 60 + 30

def fetch_stock_data():
    all_stocks = list(set([s for stocks in GROUPS.values() for s in stocks]))
    results = {}
    batch_size = 50
    for i in range(0, len(all_stocks), batch_size):
        batch = all_stocks[i:i+batch_size]
        ex_ch = "|".join([f"tse_{s}.tw" for s in batch])
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
                    change_pct = (float(z) - float(y)) / float(y) * 100
                    results[code] = {"name": name, "price": float(z), "change_pct": change_pct}
        except Exception as e:
            print(f"API錯誤: {e}")
        time.sleep(0.3)
    return results

def send_line_message(msg):
    if not GROUP_ID or not LINE_TOKEN:
        print("未設定GROUP_ID或LINE_TOKEN")
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    data = {"to": GROUP_ID, "messages": [{"type": "text", "text": msg}]}
    try:
        res = requests.post(url, headers=headers, json=data)
        print(f"LINE: {res.status_code} {res.text}")
    except Exception as e:
        print(f"LINE錯誤: {e}")

def check_stocks():
    reset_daily()
    from datetime import timezone, timedelta
    tz_taipei = timezone(timedelta(hours=8))
    now = datetime.now(tz_taipei)
    print(f"監控中 台灣時間：{now.strftime('%H:%M:%S')} 交易時間：{is_trading_time()}", flush=True)
    if not is_trading_time():
        return
    stock_data = fetch_stock_data()
    for code, info in stock_data.items():
        if code in notified:
            continue
        pct = info["change_pct"]
        group_name = STOCK_TO_GROUP.get(code, "")
        if pct >= 9.5:
            notified.add(code)
            related = []
            if group_name:
                for other_code in GROUPS.get(group_name, []):
                    if other_code != code and other_code in stock_data:
                        other_pct = stock_data[other_code]["change_pct"]
                        if other_pct >= 4.5:
                            other_name = stock_data[other_code]["name"] or other_code
                            related.append(f"{other_name} {other_code}　+{other_pct:.1f}%")
            now_str = datetime.now().strftime("%H:%M:%S")
            name = info["name"] or code
            msg = f"🚀 漲停通知｜{group_name}\n"
            msg += "━━━━━━━━━━━━━━━━\n"
            msg += f"{name} {code}　+{pct:.1f}% 🔴\n"
            msg += f"時間：{now_str}\n"
            if related:
                msg += f"\n同族群 +4.5%以上：\n"
                msg += "\n".join(related)
            send_line_message(msg)
            print(msg)

# ===== Webhook（取得群組ID）=====
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    if not body:
        return "OK", 200
    for event in body.get("events", []):
        source = event.get("source", {})
        group_id = source.get("groupId", "")
        reply_token = event.get("replyToken", "")
        if group_id and reply_token:
            requests.post(
                "https://api.line.me/v2/bot/message/reply",
                headers={"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"},
                json={"replyToken": reply_token, "messages": [{"type": "text", "text": f"群組ID：\n{group_id}"}]}
            )
    return "OK", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

# 背景監控執行緒
def monitor_loop():
    while True:
        try:
            check_stocks()
        except Exception as e:
            print(f"監控錯誤: {e}")
        time.sleep(10)

# 啟動背景執行緒
monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

@app.route("/test", methods=["GET"])
def test():
    msg = """🚀 測試通知｜散熱冷卻｜氣冷與核心組件
━━━━━━━━━━━━━━━━
奇鋐 3017　+10.0% 🔴
時間：10:23:45

同族群 +4.5%以上：
雙鴻 3324　+6.2%
健策 3653　+5.1%

⚠️ 此為系統測試訊息"""
    send_line_message(msg)
    return "測試訊息已發送！", 200
