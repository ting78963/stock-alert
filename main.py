import os
import time
import requests
import threading
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

LINE_TOKEN = os.environ.get("LINE_TOKEN", "")
GROUP_ID = os.environ.get("GROUP_ID", "")

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

GROUPS_DISPLAY = {
    "IC設計": [("世芯-KY","3661"),("創意","3443"),("智原","3035"),("威盛","2388"),("九暘","8040"),("譜瑞-KY","4966"),("全科","3209"),("矽統","2363"),("凌陽","2401"),("矽力-KY","6415")],
    "IC通路商": [("聯詠","3034"),("瑞昱","2379")],
    "矽晶圓": [("環球晶","6488"),("台勝科","3532"),("合晶","6182"),("嘉晶","3016"),("中美晶","5483"),("漢磊","3707"),("太極","4934"),("昇陽半導體","8028"),("中砂","1560"),("辛耘","3583"),("精材","3374")],
    "成熟製程代工": [("聯電","2303"),("世界","5347"),("力積電","6770")],
    "半導體設備": [("辛耘","3583"),("弘塑","3131"),("萬潤","6187"),("昇陽半導體","8028"),("志聖","2467"),("群翊","6664"),("均豪","5443"),("德律","3030"),("牧德","3563"),("晶彩科","3535"),("家登","3680"),("敘豐","3485"),("鈦昇","8027"),("東捷","8064"),("安強","6640"),("雷科","6207")],
    "先進封測": [("日月光投控","3711"),("力成","6239"),("矽格","6257"),("頎邦","6147"),("南茂","8150"),("京元電子","2449"),("台星科","3265"),("矽創","8016"),("華泰","2329")],
    "探針封測": [("穎崴","6515"),("旺矽","6223"),("精測","6510"),("中探針","6217")],
    "ABF載板": [("欣興","3037"),("南電","8046"),("景碩","3189"),("臻鼎-KY","4958")],
    "記憶體": [("南亞科","2408"),("華邦電","2344"),("愛普","6531"),("威剛","3260"),("至上","8112"),("旺宏","2337"),("晶豪科","3006"),("鈺創","5351"),("群聯","8299"),("宜鼎","5289"),("力積電","6770"),("青雲","5386"),("擎亞","8096"),("凌航","3135"),("宇瞻","8271"),("創見","2451"),("十銓","4967")],
    "IPC邊緣AI": [("研華","2395"),("技嘉","2376"),("微星","2377"),("樺漢","6414"),("華碩","2357"),("凌華","6166"),("立端","6245"),("泓格","3577"),("研揚","6579"),("磐儀","3594"),("英業達","2356"),("宏碁","2353"),("和碩","4938"),("茂訊","3213")],
    "AI伺服器": [("鴻海","2317"),("緯穎","6669"),("緯創","3231"),("廣達","2382")],
    "散熱": [("奇鋐","3017"),("雙鴻","3324"),("健策","3653"),("高力","8996"),("晟銘電","3013"),("建準","2421"),("富世達","6805"),("一詮","2486")],
    "光通訊": [("聯亞","3081"),("上詮","3363"),("波若威","3163"),("光聖","6442"),("訊芯-KY","6451"),("眾達-KY","4977"),("華星光","4979"),("聯鈞","3450"),("全新","2455"),("穩懋","3105"),("IET-KY","4971"),("環宇-KY","4991"),("光環","3234"),("創威","6530"),("聯光通","4903"),("正文","4906"),("前鼎","4908"),("宏捷科","8086"),("台表科","6278"),("毅嘉","2402"),("瑞軒","2489")],
    "低軌衛星": [("華通","2313"),("昇達科","3491"),("啟碁","6285"),("燿華","2367"),("穩懋","3105"),("兆赫","2485"),("耀登","3138"),("宏捷科","8086"),("同欣電","6271"),("敬鵬","2355"),("聯德","4912"),("信錦","1582"),("事欣科","4916")],
    "被動元件": [("國巨","2327"),("華新科","2492"),("凱美","2375"),("禾伸堂","3026"),("鈺邦","6449"),("佳邦","6284"),("千如","3236"),("臺慶科","3357"),("大毅","2478"),("光頡","3624"),("日電貿","3090"),("信昌電","6173"),("立隆電","2472"),("三集瑞-KY","6862"),("達方","8163"),("九豪","6127"),("松上","6175"),("金山電","8042"),("鈞寶","6155"),("堡達","3537"),("密望實","8043"),("越峰","8121")],
    "石英元件": [("晶技","3042"),("希華","2484"),("台嘉碩","3221"),("加高","8182"),("安碁","6174"),("泰藝","8289")],
    "功率元件": [("強茂","2481"),("德微","3675"),("台半","5425"),("朋程","8255"),("茂達","6138"),("富鼎","8261")],
    "機器人": [("上銀","2049"),("直得","1597"),("盟立","2464"),("羅昇","8374"),("達明","4562"),("東元","4526"),("台灣精銳","1536"),("所羅門","2359"),("廣宇","2328")],
    "廠務工程": [("漢唐","2404"),("亞翔","6139"),("聖暉","5536"),("帆宣","6196"),("漢科","3402"),("晟呈","4768"),("立盈","7820"),("兆聯實業","6944")],
    "重電": [("華城","1519"),("中興電","1513"),("士電","1503"),("亞力","1514")],
    "PCB高階": [("尖點","8021"),("凱崴","5498"),("鉅橡","8074"),("金居","8358"),("碩天","3645")],
    "PCB玻纖布": [("德宏","5475"),("富喬","1815"),("台玻","1802"),("南亞","1303"),("建榮","5340")],
    "光學鏡頭": [("大立光","3008"),("先進光","3362"),("玉晶光","3406"),("揚明光","3504"),("今國光","6209"),("亞光","3019"),("佳凌","4976")],
    "玻璃基板": [("群創","3481"),("東捷","8064"),("正達","3149"),("雷科","6207")],
    "連接線": [("嘉澤","3533"),("貿聯-KY","3665"),("佳必琪","6197"),("嘉基","6715"),("信邦","3023")],
    "電源供應": [("台達電","2308"),("光寶科","2301"),("康舒","6282"),("群電","6412")],
    "導線架": [("順德","2351"),("長科","6548"),("界霖","5285"),("長華","8070"),("百容","2483")],
    "BBU備援電池": [("AES-KY","6781"),("順達","3211"),("新盛力","4931"),("系統電","5309"),("加百裕","3323")],
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
                if code and z not in ["-",""] and y not in ["-",""] and float(y) > 0:
                    change_pct = (float(z) - float(y)) / float(y) * 100
                    is_limit_up = change_pct >= 9.5
                    results[code] = {"name": name, "change_pct": change_pct, "is_limit_up": is_limit_up}
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
            high = []
            mid = []
            if group_name:
                for other_code in GROUPS.get(group_name, []):
                    if other_code != code and other_code in stock_data:
                        other_pct = stock_data[other_code]["change_pct"]
                        other_name = stock_data[other_code]["name"] or other_code
                        if other_pct >= 4.0:
                            high.append(f"{other_name} {other_code}\u3000+{other_pct:.1f}%")
                        elif other_pct >= 3.0:
                            mid.append(f"{other_name} {other_code}\u3000+{other_pct:.1f}%")
            now_str = now.strftime("%H:%M:%S")
            name = info["name"] or code
            pct = info["change_pct"]
            msg = f"\U0001f680 漲停通知｜{group_name}\n"
            msg += "\u2501" * 16 + "\n"
            msg += f"{name} {code}\u3000+{pct:.1f}% \U0001f534\n"
            msg += f"時間：{now_str}\n"
            if high:
                msg += f"\n同族群 4%以上：\n" + "\n".join(high)
            if mid:
                msg += f"\n\n同族群 3~4%：\n" + "\n".join(mid)
            send_line_message(msg)
            print(msg, flush=True)

# ══════════════════════════════════════════════
# 新增：國際指數 endpoint
# ══════════════════════════════════════════════
@app.route("/market", methods=["GET"])
def market():
    SYMBOLS = {
        "nasdaq": "^IXIC",
        "sox":    "^SOX",
        "sp500":  "^GSPC",
        "tsm":    "TSM",
        "nvda":   "NVDA",
        "vix":    "^VIX",
        "nikkei": "^N225",
        "kospi":  "^KS11",
    }
    result = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for key, symbol in SYMBOLS.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
            res = requests.get(url, headers=headers, timeout=8)
            data = res.json()
            meta = data["chart"]["result"][0]["meta"]
            close = meta.get("regularMarketPrice", 0)
            prev  = meta.get("chartPreviousClose", 0) or meta.get("previousClose", 0)
            chg_pct = ((close - prev) / prev * 100) if prev else 0
            result[key] = {"close": round(close, 2), "prev": round(prev, 2), "chg_pct": round(chg_pct, 2)}
        except Exception as e:
            result[key] = None
            print(f"market {key} 錯誤: {e}", flush=True)
    response = jsonify(result)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

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
                reply_msg = "📊 族群清單查詢\n點此查看所有族群股票：\nhttps://stock-alert-91j1.onrender.com/groups"
                requests.post(
                    "https://api.line.me/v2/bot/message/reply",
                    headers={"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"},
                    json={"replyToken": reply_token, "messages": [{"type": "text", "text": reply_msg}]}
                )
    return "OK", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

@app.route("/test", methods=["GET"])
def test():
    msg = "\U0001f680 漲停通知｜散熱\n" + "\u2501"*16 + "\n奇鋐 3017\u3000+10.0% \U0001f534\n時間：10:23:45\n\n同族群 4%以上：\n雙鴻 3324\u3000+6.2%\n健策 3653\u3000+5.1%\n\n同族群 3~4%：\n高力 8996\u3000+3.8%\n\n⚠️ 此為系統測試訊息"
    send_line_message(msg)
    return "測試訊息已發送！", 200

@app.route("/testotc", methods=["GET"])
def testotc():
    ex_ch = "tse_1815.tw|otc_1815.tw|tse_3017.tw|otc_3017.tw"
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        result = ""
        for item in data.get("msgArray", []):
            code = item.get("c",""); name = item.get("n",""); z = item.get("z","-"); ex = item.get("ex","")
            result += f"{name} {code} 市場:{ex} 現價:{z}\n"
        return result or "沒有資料", 200
    except Exception as e:
        return f"錯誤: {e}", 500

@app.route("/groups", methods=["GET"])
def groups():
    SECTIONS = {
        "半導體": ["IC設計","IC通路商","矽晶圓","成熟製程代工","半導體設備","先進封測","探針封測","ABF載板","記憶體"],
        "AI / 伺服器": ["AI伺服器","IPC邊緣AI","散熱","電源供應","BBU備援電池"],
        "通訊 / 衛星": ["光通訊","低軌衛星","連接線"],
        "被動 / 功率元件": ["被動元件","石英元件","功率元件","導線架"],
        "基板 / 材料": ["PCB高階","PCB玻纖布","玻璃基板"],
        "其他": ["機器人","廠務工程","重電","光學鏡頭","LED"],
    }
    html = """<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>族群清單｜台股漲停通知</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f0;color:#1a1a1a;padding:16px}.header{margin-bottom:20px}.header h1{font-size:22px;font-weight:600}.header p{font-size:13px;color:#888;margin-top:4px}.section{margin-bottom:24px}.section-title{font-size:11px;font-weight:600;color:#888;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px}.group{background:#fff;border-radius:12px;padding:14px 16px;margin-bottom:8px;border:1px solid #ebebeb}.gname{font-size:14px;font-weight:600;color:#111;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}.gcnt{font-size:11px;color:#aaa;font-weight:400;background:#f5f5f0;padding:2px 8px;border-radius:20px}.tags{display:flex;flex-wrap:wrap;gap:7px}.tag{background:#f8f8f6;border:1px solid #e8e8e4;border-radius:8px;padding:7px 13px;font-size:14px;color:#333;white-space:nowrap}.code{color:#e8192c;font-size:12px;margin-left:4px;font-weight:500}</style></head><body>
<div class="header"><h1>🚀 族群清單</h1><p>台股漲停通知 @541etrau｜29個族群</p></div>"""
    for section_name, group_names in SECTIONS.items():
        html += f'<div class="section"><div class="section-title">{section_name}</div>'
        for gname in group_names:
            if gname in GROUPS_DISPLAY:
                stocks = GROUPS_DISPLAY[gname]
                html += f'<div class="group"><div class="gname">{gname}<span class="gcnt">{len(stocks)} 支</span></div><div class="tags">'
                for sname, code in stocks:
                    html += f'<span class="tag">{sname}<span class="code">{code}</span></span>'
                html += '</div></div>'
        html += '</div>'
    html += '</body></html>'
    return html

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
