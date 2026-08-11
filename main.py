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

TZ = timezone(timedelta(hours=8))

# ===== 訊號參數 =====
FIRST_MULT = 1.25          # ⚡觸發倍數
SECOND_MULT = round(math.sqrt(1.25), 3)  # 🔥(A)倍數 = 1.118
WARN_RATIO = 0.8           # 回落警示比例（內部用）
TRAIL_RATIO = 0.9          # 移動停利比例
TRACK_MIN_PCT = 3.0        # 追蹤起始門檻
TRACK_MAX_PCT = 6.0        # 起始超過此值：追蹤但不通知
FIRE_MAX_PCT = 6.5         # 🔥觸發點上限（超過不通知）
SIGNAL_CUTOFF = 12         # 12:00後不追新⚡
MAX_LIMIT_UP_NOTIFY = 3    # 同族群最多發幾次漲停通知

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
    "被動元件": [("國巨","2327"),("華新科","2492"),("凱美","2375"),("禾伸堂","3026"),("鈺邦","6449"),("佳邦","6284"),("千如","3236"),("臺慶科","3357"),("大毅","2478"),("光頡","3624"),("日電貿","3090"),("信昌電","6173"),("立隆電","2472"),("蜜望實","8043"),("越峰","8121")],
    "石英元件": [("晶技","3042"),("希華","2484"),("台嘉碩","3221"),("加高","8182"),("安碁","6174"),("泰藝","8289")],
    "功率元件": [("強茂","2481"),("德微","3675"),("台半","5425"),("朋程","8255"),("茂達","6138"),("富鼎","8261")],
    "機器人": [("上銀","2049"),("直得","1597"),("盟立","2464"),("羅昇","8374"),("達明","4562"),("東元","4526"),("台灣精銳","1536"),("所羅門","2359"),("廣宇","2328")],
    "廠務工程": [("漢唐","2404"),("亞翔","6139"),("聖暉","5536"),("帆宣","6196"),("漢科","3402"),("晶呈","4768"),("立盈","7820"),("兆聯實業","6944")],
    "重電": [("華城","1519"),("中興電","1513"),("士電","1503"),("亞力","1514")],
    "PCB高階": [("尖點","8021"),("凱崴","5498"),("鉅橡","8074"),("金居","8358"),("達邁","3645")],
    "PCB玻纖布": [("德宏","5475"),("富喬","1815"),("台玻","1802"),("南亞","1303"),("建榮","5340")],
    "光學鏡頭": [("大立光","3008"),("先進光","3362"),("玉晶光","3406"),("揚明光","3504"),("今國光","6209"),("亞光","3019")],
    "玻璃基板": [("群創","3481"),("東捷","8064"),("正達","3149"),("雷科","6207")],
    "LED": [("惠特","6706"),("GIS-KY","6456"),("光鋐","6226"),("巨虹","2426"),("光磊","4956"),("其陽","3714"),("榮創","3437"),("泰谷","3339"),("宏芯","6168"),("動力-KY","8215"),("采鈺","6789")],
    "連接線": [("嘉澤","3533"),("貿聯-KY","3665"),("佳必琪","6197"),("嘉基","6715"),("信邦","3023")],
    "電源供應": [("台達電","2308"),("光寶科","2301"),("康舒","6282"),("群電","6412")],
    "導線架": [("順德","2351"),("長科","6548"),("界霖","5285"),("長華","8070"),("百容","2483")],
    "BBU備援電池": [("AES-KY","6781"),("順達","3211"),("新盛力","4931"),("系統電","5309"),("加百裕","3323")],
}

STOCK_TO_GROUP = {}
STOCK_TO_NAME = {}
for group_name, stocks in GROUPS.items():
    for stock in stocks:
        if stock not in STOCK_TO_GROUP:
            STOCK_TO_GROUP[stock] = group_name

for group_name, stocks in GROUPS_DISPLAY.items():
    for name, code in stocks:
        STOCK_TO_NAME[code] = name

# ===== 狀態變數 =====
notified_limit_up = set()       # 已發漲停通知的股票
group_limit_up_count = {}       # {group: 漲停次數}
group_triggered = set()         # 今天有漲停的族群

# tracking結構：{code: {
#   name, group, start_pct,
#   spark_pct,          # ⚡觸發點（固定，不浮動）
#   spark_confirmed,    # API確認兩次
#   had_pullback,       # 是否經過回落（內部標記）
#   pullback_low,       # 回落最低點
#   fire_pct,           # 🔥觸發點
#   fired,              # 已發🔥通知
#   peak_pct,           # 🔥後最高點
#   trail_notified,     # 已發移動停利通知
# }}
tracking = {}

# 待發🔥訊號（批次合併發送）
pending_fire = []

# 收盤記錄
daily_records = []
closing_done_date = None

def now_taipei():
    return datetime.now(TZ)

def is_trading_time():
    now = now_taipei()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 13 * 60 + 30

def can_add_spark():
    """12:00前才能追新⚡"""
    now = now_taipei()
    return now.hour < SIGNAL_CUTOFF

def send_line(msg):
    if not GROUP_ID or not LINE_TOKEN:
        print(msg, flush=True)
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    data = {"to": GROUP_ID, "messages": [{"type": "text", "text": msg}]}
    try:
        res = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"LINE: {res.status_code}", flush=True)
    except Exception as e:
        print(f"LINE錯誤: {e}", flush=True)

def fetch_stocks(codes):
    """抓指定代號的即時資料"""
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
                name = item.get("n", "") or STOCK_TO_NAME.get(code, code)
                z = item.get("z", "-")
                y = item.get("y", "-")
                if code and z not in ["-",""] and y not in ["-",""] and float(y) > 0:
                    pct = round((float(z) - float(y)) / float(y) * 100, 2)
                    results[code] = {
                        "name": name,
                        "pct": pct,
                        "price": float(z),
                        "prev_close": float(y),
                        "is_limit_up": pct >= 9.5
                    }
        except Exception as e:
            print(f"API錯誤: {e}", flush=True)
        time.sleep(0.2)
    return results

def add_to_tracking(code, name, group, start_pct):
    """加入追蹤（族群漲停當下的真實起始點）"""
    if code in tracking:
        return
    tracking[code] = {
        "name": name,
        "group": group,
        "start_pct": start_pct,
        "spark_pct": None,
        "spark_count": 0,        # 連續確認次數（避免API異常）
        "had_pullback": False,
        "pullback_low": None,
        "fire_pct": None,
        "fired": False,
        "peak_pct": None,
        "trail_notified": False,
    }

def on_group_limit_up(code, group, stock_data):
    """族群漲停當下，立即處理同族群股票"""
    now = now_taipei()
    now_str = now.strftime("%H:%M:%S")
    name = stock_data.get(code, {}).get("name") or STOCK_TO_NAME.get(code, code)
    pct = stock_data.get(code, {}).get("pct", 0)

    # 計算漲停次數
    count = group_limit_up_count.get(group, 0) + 1
    group_limit_up_count[group] = count
    group_triggered.add(group)

    if count > MAX_LIMIT_UP_NOTIFY:
        # 超過三次，只加入追蹤不發通知
        for other_code in GROUPS.get(group, []):
            if other_code == code or other_code in notified_limit_up:
                continue
            if other_code in stock_data:
                other_pct = stock_data[other_code]["pct"]
                other_name = stock_data[other_code]["name"] or STOCK_TO_NAME.get(other_code, other_code)
                if TRACK_MIN_PCT <= other_pct and other_code not in tracking:
                    add_to_tracking(other_code, other_name, group, other_pct)
        return

    # 建立同族群股票漲幅列表（3%以上）
    group_stocks_lines = []
    for other_code in GROUPS.get(group, []):
        if other_code == code or other_code in notified_limit_up:
            continue
        if other_code not in stock_data:
            continue
        other_pct = stock_data[other_code]["pct"]
        other_name = stock_data[other_code]["name"] or STOCK_TO_NAME.get(other_code, other_code)

        if other_pct >= 9.5:
            # 已漲停的也列出
            group_stocks_lines.append((other_code, other_name, other_pct, True))
        elif other_pct >= TRACK_MIN_PCT:
            group_stocks_lines.append((other_code, other_name, other_pct, False))
            # 加入追蹤
            if other_code not in tracking:
                add_to_tracking(other_code, other_name, group, other_pct)

    # 判斷今日資金進駐
    has_momentum = any(p >= TRACK_MIN_PCT for _, _, p, _ in group_stocks_lines)
    momentum_tag = "今日資金進駐 ✅" if has_momentum else "今日資金進駐 ❌"

    # 發漲停通知
    msg = f"🚀 漲停通知｜{group}\n"
    msg += "━━━━━━━━━━━━━━━━\n"
    msg += f"{name} {code}　+{pct:.1f}% 🔴 漲停\n"
    msg += f"時間：{now_str}　第{count}支\n"
    msg += f"{momentum_tag}\n"

    if group_stocks_lines:
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "同族群當下漲幅：\n"
        # 按漲幅排序
        group_stocks_lines.sort(key=lambda x: x[2], reverse=True)
        for c, n, p, is_lu in group_stocks_lines:
            lu_tag = " 🔴" if is_lu else ""
            msg += f"{n} {c}　+{p:.1f}%{lu_tag}\n"

    send_line(msg)
    print(msg, flush=True)

def send_pending_fire():
    """發送批次🔥訊號"""
    global pending_fire
    if not pending_fire:
        return

    now = now_taipei()
    now_str = now.strftime("%H:%M")
    msg = f"🔥 確認突破｜{now_str}\n"

    for item in pending_fire:
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"{item['name']} {item['code']}｜{item['group']}\n"
        remaining = round(9.0 - item['fire_pct'], 2)

        if item['type'] == 'B':
            msg += f"起始+{item['start_pct']:.1f}% → 🔥+{item['fire_pct']:.2f}% ⚠️考驗通過\n"
        else:
            msg += f"起始+{item['start_pct']:.1f}% → 🔥+{item['fire_pct']:.2f}% 直接突破\n"
            msg += f"⚡未經回落，謹慎操作\n"

        msg += f"剩餘空間：+{remaining:.2f}%\n"

        # 記錄
        daily_records.append({
            "code": item['code'],
            "name": item['name'],
            "group": item['group'],
            "start_pct": item['start_pct'],
            "fire_pct": item['fire_pct'],
            "fire_type": item['type'],
            "fire_time": now_str,
            "signals": item['signals'],
            "peak_pct": None,
            "trail_pct": None,
            "close_pct": None,
        })

    send_line(msg)
    print(msg, flush=True)
    pending_fire = []

def process_tracking(stock_data):
    """處理追蹤中的股票"""
    global pending_fire
    fire_batch = []

    for code, t in list(tracking.items()):
        if code not in stock_data:
            continue

        info = stock_data[code]
        pct = info["pct"]
        name = info["name"] or t["name"]

        # 漲停 → 立即移除
        if info["is_limit_up"]:
            del tracking[code]
            continue

        group = t["group"]
        start_pct = t["start_pct"]
        spark_pct = t["spark_pct"]
        had_pullback = t["had_pullback"]
        fire_pct = t["fire_pct"]
        fired = t["fired"]
        peak_pct = t["peak_pct"]

        if fired:
            # ===== 🔥後：追蹤移動停利 =====
            if pct > (peak_pct or 0):
                tracking[code]["peak_pct"] = pct
                peak_pct = pct

            if peak_pct is not None:
                trail_threshold = round(peak_pct * TRAIL_RATIO, 2)
                if pct <= trail_threshold and not t["trail_notified"]:
                    # 發移動停利通知
                    msg = f"⚠️ 移動停利｜{name} {code}\n"
                    msg += "━━━━━━━━━━━━━━━━\n"
                    msg += f"族群：{group}\n"
                    msg += f"進場：🔥+{fire_pct:.2f}%\n"
                    msg += f"最高：+{peak_pct:.2f}% → 停利+{trail_threshold:.2f}%\n"
                    msg += f"現在：+{pct:.2f}%\n"
                    msg += "━━━━━━━━━━━━━━━━\n"
                    msg += "建議出場！"
                    send_line(msg)
                    print(msg, flush=True)

                    # 更新記錄
                    for r in daily_records:
                        if r["code"] == code and r["trail_pct"] is None:
                            r["peak_pct"] = peak_pct
                            r["trail_pct"] = pct
                            break

                    # 立即移除
                    del tracking[code]
            continue

        # ===== 還沒🔥：處理⚡和回落 =====
        if spark_pct is None:
            # 等待⚡觸發
            if not can_add_spark():
                continue
            threshold = round(start_pct * FIRST_MULT, 2)
            if pct >= threshold:
                # 連續確認兩次避免API異常
                tracking[code]["spark_count"] = t.get("spark_count", 0) + 1
                if tracking[code]["spark_count"] >= 2:
                    tracking[code]["spark_pct"] = pct
                    tracking[code]["spark_count"] = 0
                    print(f"⚡ {name} {code} +{pct:.2f}%", flush=True)
            else:
                tracking[code]["spark_count"] = 0
        else:
            # 已有⚡，等待🔥或回落
            warn_threshold = round(spark_pct * WARN_RATIO, 2)
            fire_threshold_A = round(spark_pct * SECOND_MULT, 2)

            if not had_pullback:
                # 路線A：直接🔥
                if pct >= fire_threshold_A and pct < 9.5:
                    # 確認🔥(A)，起始超過6%且🔥超過6.5%不通知
                    should_notify = not (start_pct >= TRACK_MAX_PCT and pct > FIRE_MAX_PCT)
                    if should_notify:
                        tracking[code]["fire_pct"] = pct
                        tracking[code]["fired"] = True
                        tracking[code]["peak_pct"] = pct
                        fire_batch.append({
                            "code": code, "name": name, "group": group,
                            "start_pct": start_pct, "fire_pct": pct,
                            "type": "A",
                            "signals": f"▶→⚡→🔥"
                        })
                    else:
                        # 不通知但繼續追蹤移動停利
                        tracking[code]["fire_pct"] = pct
                        tracking[code]["fired"] = True
                        tracking[code]["peak_pct"] = pct
                elif pct <= warn_threshold:
                    # 內部標記回落，不發LINE
                    tracking[code]["had_pullback"] = True
                    tracking[code]["pullback_low"] = pct
                    print(f"⚠️內部回落 {name} {code} +{pct:.2f}%", flush=True)

            else:
                # 路線B：回落後等反彈
                if t["pullback_low"] and pct < t["pullback_low"]:
                    tracking[code]["pullback_low"] = pct

                if pct >= spark_pct and pct < 9.5:
                    # 🔥(B) 考驗後突破
                    should_notify = not (start_pct >= TRACK_MAX_PCT and pct > FIRE_MAX_PCT)
                    if should_notify:
                        tracking[code]["fire_pct"] = pct
                        tracking[code]["fired"] = True
                        tracking[code]["peak_pct"] = pct
                        fire_batch.append({
                            "code": code, "name": name, "group": group,
                            "start_pct": start_pct, "fire_pct": pct,
                            "type": "B",
                            "signals": f"▶→⚡→⚠️→🔥"
                        })
                    else:
                        tracking[code]["fire_pct"] = pct
                        tracking[code]["fired"] = True
                        tracking[code]["peak_pct"] = pct

                elif pct <= warn_threshold:
                    # 🔥(A)路線：⚠️後移除（只給一次機會）
                    # 🔥(B)路線：繼續等
                    pass  # B路線繼續等待反彈

    # 發批次🔥通知（只有B型才發）
    # 根據討論：只發⚠️考驗後的🔥(B)
    b_fires = [f for f in fire_batch if f["type"] == "B"]
    if b_fires:
        pending_fire = b_fires
        send_pending_fire()

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
                c = item.get("c", "")
                h = item.get("h", "-")
                z = item.get("z", "-")
                y = item.get("y", "-")
                if c and h not in ["-",""] and y not in ["-",""] and float(y) > 0:
                    final_data[c] = {
                        "high_pct": round((float(h)-float(y))/float(y)*100, 2),
                        "close_pct": round((float(z)-float(y))/float(y)*100, 2) if z not in ["-",""] else None
                    }
        except Exception as e:
            print(f"收盤查詢錯誤: {e}", flush=True)
        time.sleep(0.2)

    # 更新記錄
    for r in daily_records:
        final = final_data.get(r["code"], {})
        r["high_pct"] = final.get("high_pct")
        r["close_pct"] = final.get("close_pct")

    today_str = now_taipei().strftime("%Y-%m-%d")

    # 讀取歷史並push
    history = {}
    try:
        raw_url = "https://raw.githubusercontent.com/ting78963/stock/main/stats.json"
        res = requests.get(raw_url, timeout=10)
        if res.status_code == 200:
            history = res.json()
    except:
        pass
    history[today_str] = daily_records
    push_to_github("stats.json", history)

    # 計算勝率
    fired = [r for r in daily_records if r.get("fire_pct")]
    won = [r for r in fired if r.get("high_pct") and r["high_pct"] >= 9.0]
    lost = [r for r in fired if r.get("high_pct") and r["high_pct"] < r.get("fire_pct", 0)]
    trailed = [r for r in fired if r.get("trail_pct")]

    msg = f"📊 收盤統計｜{today_str}\n"
    msg += "━━━━━━━━━━━━━━━━\n"
    msg += f"🔥訊號：{len(fired)}隻\n"
    if fired:
        win_rate = len(won)/len(fired)*100
        msg += f"勝率（到9%）：{len(won)}/{len(fired)} = {win_rate:.0f}%\n"
        msg += f"移動停利觸發：{len(trailed)}隻\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        for r in fired:
            high = f"+{r['high_pct']:.1f}%" if r.get("high_pct") else "?"
            fire = f"+{r['fire_pct']:.2f}%"
            typ = "⚠️考驗" if r.get("fire_type") == "B" else "直接"
            win = "✅" if r.get("high_pct") and r["high_pct"] >= 9.0 else "❌"
            msg += f"{win} {r['name']} {r['code']} {typ}\n"
            msg += f"   🔥{fire} → 最高{high}\n"

    send_line(msg)
    print(f"收盤統計完成，共{len(fired)}筆🔥", flush=True)
    daily_records.clear()

def push_to_github(filename, content):
    if not GITHUB_TOKEN:
        return
    repo = "ting78963/stock-alert"
    api_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    sha = None
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code == 200:
            sha = res.json().get("sha")
    except:
        pass
    content_b64 = base64.b64encode(json.dumps(content, ensure_ascii=False, indent=2).encode()).decode()
    data = {"message": f"Update {filename}", "content": content_b64}
    if sha:
        data["sha"] = sha
    try:
        res = requests.put(api_url, headers=headers, json=data, timeout=15)
        print(f"GitHub push: {res.status_code}", flush=True)
    except Exception as e:
        print(f"GitHub push錯誤: {e}", flush=True)

def check_closing_time():
    global closing_done_date
    now = now_taipei()
    today_str = now.strftime("%Y-%m-%d")
    t = now.hour * 60 + now.minute
    if 13*60+30 <= t <= 13*60+35 and closing_done_date != today_str and now.weekday() < 5:
        do_closing_summary()
        closing_done_date = today_str

def check_stocks():
    now = now_taipei()
    print(f"監控中 {now.strftime('%H:%M:%S')} 交易時間：{is_trading_time()}", flush=True)

    if not is_trading_time():
        notified_limit_up.clear()
        group_limit_up_count.clear()
        group_triggered.clear()
        tracking.clear()
        daily_records.clear()
        return

    # 抓所有股票資料
    all_codes = list(set([s for stocks in GROUPS.values() for s in stocks] + list(tracking.keys())))
    stock_data = fetch_stocks(all_codes)

    # 處理追蹤中的股票（移動停利、🔥等）
    process_tracking(stock_data)

    # 偵測新漲停
    for code, info in stock_data.items():
        if code in notified_limit_up:
            continue
        if not info["is_limit_up"]:
            continue

        group = STOCK_TO_GROUP.get(code, "")
        if not group:
            continue

        notified_limit_up.add(code)

        # 漲停股票立即從tracking移除
        if code in tracking:
            del tracking[code]

        # 處理族群漲停
        on_group_limit_up(code, group, stock_data)

    # 已觸發族群持續掃描新進3%的股票
    for group in group_triggered:
        for code in GROUPS.get(group, []):
            if code in notified_limit_up or code in tracking:
                continue
            if code not in stock_data:
                continue
            pct = stock_data[code]["pct"]
            if TRACK_MIN_PCT <= pct and can_add_spark():
                name = stock_data[code]["name"] or STOCK_TO_NAME.get(code, code)
                add_to_tracking(code, name, group, pct)

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
                requests.post(
                    "https://api.line.me/v2/bot/message/reply",
                    headers={"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"},
                    json={"replyToken": reply_token, "messages": [{"type": "text", "text": "📊 族群清單：\nhttps://stock-alert-91j1.onrender.com/groups"}]}
                )
    return "OK", 200

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/test")
def test():
    msg = "🔥 確認突破｜09:22\n━━━━━━━━━━━━━━━━\n聯光通 4903｜光通訊\n起始+3.1% → 🔥+3.92% ⚠️考驗通過\n剩餘空間：+5.08%\n━━━━━━━━━━━━━━━━\n⚠️ 此為系統測試"
    send_line(msg)
    return "測試訊息已發送！", 200

@app.route("/status")
def status():
    now = now_taipei()
    return {
        "time": now.strftime("%H:%M:%S"),
        "tracking": len(tracking),
        "notified": len(notified_limit_up),
        "group_triggered": list(group_triggered),
        "group_limit_up_count": group_limit_up_count,
        "daily_records": len(daily_records),
    }

@app.route("/groups")
def groups_page():
    SECTIONS = {
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
    for sec, gnames in SECTIONS.items():
        html += f'<div class="st" style="margin-bottom:10px">{sec}</div>'
        for gname in gnames:
            if gname in GROUPS_DISPLAY:
                stocks = GROUPS_DISPLAY[gname]
                html += f'<div class="g"><div class="gn">{gname}<span class="gc">{len(stocks)}支</span></div><div class="tags">'
                for sname, code in stocks:
                    html += f'<span class="tag">{sname}<span class="code">{code}</span></span>'
                html += '</div></div>'
    html += '</body></html>'
    return html

def monitor_loop():
    while True:
        try:
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
