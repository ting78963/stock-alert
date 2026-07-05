import os
import time
import requests
import threading
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)

LINE_TOKEN = os.environ.get("LINE_TOKEN", "")
GROUP_ID = os.environ.get("GROUP_ID", "")

GROUPS = {
    "IC設計": ["3661","3443","3035","2388","8040","4966","3209","2363","2401","6415"],
    "IC通路商": ["3034","2379"],
    "矽晶圓": ["6488","3532","6182","3016","5483","3707","4934","8028","1560","3583","3374"],
    "成熟製程代工": ["2303","5347","6770"],
    "半導體設備": ["3583","3131","6187","8028","1560","2467","6664","5443","3030","3563","3167","3535","3455","3680","7769","3485","8027","8064","6640","6207"],
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
for group_name, stocks in GROUPS.items():
    for stock in stocks:
        if stock not in STOCK_TO_GROUP:
            STOCK_TO_GROUP[stock] = group_name

notified = set()

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
    batch_size = 25
    for i in range(0, len(all_stocks), batch_size):
        batch = all_stocks[i:i+batch_size]
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
                u = item.get("u", "-")
                if code and z not in ["-",""] and y not in ["-",""] and float(y) > 0:
                    change_pct = (float(z) - float(y)) / float(y) * 100
                    is_limit_up = (u not in ["-",""] and abs(float(z) - float(u)) < 0.01)
                    results[code] = {
                        "name": name,
                        "change_pct": change_pct,
                        "is_limit_up": is_limit_up
                    }
        except Exception as e:
            print(f"API錯誤: {e}", flush=True)
        time.sleep(0.2)
    return results

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

def check_stocks():
    from datetime import timezone, timedelta
    tz_taipei = timezone(timedelta(hours=8))
    now = datetime.now(tz_taipei)
    print(f"監控中 台灣時間：{now.strftime('%H:%M:%S')} 交易時間：{is_trading_time()}", flush=True)
    if not is_trading_time():
        notified.clear()
        return
    stock_data = fetch_stock_data()
    for code, info in stock_data.items():
        if code in notified:
            continue
        if info["is_limit_up"]:
            notified.add(code)
            group_name = STOCK_TO_GROUP.get(code, "")
            
            # 同族群分兩層
            high = []   # 4%以上
            mid = []    # 3~4%
            
            if group_name:
                for other_code in GROUPS.get(group_name, []):
                    if other_code != code and other_code in stock_data:
                        other_pct = stock_data[other_code]["change_pct"]
                        other_name = stock_data[other_code]["name"] or other_code
                        if other_pct >= 4.0:
                            high.append(f"{other_name} {other_code}　+{other_pct:.1f}%")
                        elif other_pct >= 3.0:
                            mid.append(f"{other_name} {other_code}　+{other_pct:.1f}%")

            now_str = now.strftime("%H:%M:%S")
            name = info["name"] or code
            pct = info["change_pct"]
            
            msg = f"🚀 漲停通知｜{group_name}\n"
            msg += "━━━━━━━━━━━━━━━━\n"
            msg += f"{name} {code}　+{pct:.1f}% 🔴\n"
            msg += f"時間：{now_str}\n"
            if high:
                msg += f"\n同族群 4%以上：\n"
                msg += "\n".join(high)
            if mid:
                msg += f"\n\n同族群 3~4%：\n"
                msg += "\n".join(mid)
            
            send_line_message(msg)
            print(msg, flush=True)

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

@app.route("/test", methods=["GET"])
def test():
    msg = """🚀 漲停通知｜散熱
━━━━━━━━━━━━━━━━
奇鋐 3017　+10.0% 🔴
時間：10:23:45

同族群 4%以上：
雙鴻 3324　+6.2%
健策 3653　+5.1%

同族群 3~4%：
高力 8996　+3.8%
晟銘電 3013　+3.2%

⚠️ 此為系統測試訊息"""
    send_line_message(msg)
    return "測試訊息已發送！", 200

def monitor_loop():
    while True:
        try:
            check_stocks()
        except Exception as e:
            print(f"監控錯誤: {e}", flush=True)
        time.sleep(5)

monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
