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
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")

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

# tracking結構（族群系統）
tracking = {}

# 黃金奇點系統
golden_codes = set()       # 101~130元的股票代號（收盤後更新）
golden_tracking = {}       # 獨立追蹤字典（邏輯與tracking相同）
golden_update_date = None  # 上次更新黃金奇點清單的日期
golden_snapshot_done = False  # 今天09:10快照是否已完成

# 待發🔥訊號（批次合併發送）
pending_fire = []

# 收盤記錄
daily_records = []    # 族群系統
golden_records = []   # 黃金奇點系統
closing_done_date = None
noon_done_date = None  # 12:00 停利通知是否已發

def now_taipei():
    return datetime.now(TZ)

def is_trading_time():
    now = now_taipei()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 13 * 60 + 30

def can_add_new_tracking():
    """12:00前才能追新族群股票"""
    now = now_taipei()
    return now.hour < SIGNAL_CUTOFF

def send_line(msg):
    """純文字訊息（保留作 fallback）"""
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

def send_flex(flex_message):
    """發送 Flex Message"""
    if not GROUP_ID or not LINE_TOKEN:
        print(json.dumps(flex_message, ensure_ascii=False, indent=2), flush=True)
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    data = {"to": GROUP_ID, "messages": [flex_message]}
    try:
        res = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"LINE Flex: {res.status_code}", flush=True)
    except Exception as e:
        print(f"LINE Flex錯誤: {e}", flush=True)

# ===== Flex Message 顏色常數 =====
C_WINE   = "#8b1a1a"   # 漲停通知 header
C_RED    = "#dc2626"   # 買進 header / 動作區
C_GREEN  = "#16a34a"   # 出場 header / 動作區
C_GOLD   = "#facc15"   # 黃金奇點文字
C_WHITE  = "#ffffff"
C_TEXT   = "#1a1a1a"
C_LABEL  = "#aaaaaa"
C_BORDER = "#f0f0f0"

def _row(label, value, value_color=None):
    """Flex 單行 label / value"""
    color = value_color or C_TEXT
    return {
        "type": "box",
        "layout": "horizontal",
        "paddingTop": "5px",
        "paddingBottom": "5px",
        "borderWidth": "0px",
        "contents": [
            {"type": "text", "text": label, "color": C_LABEL, "size": "sm", "flex": 3},
            {"type": "text", "text": value, "color": color, "size": "sm", "flex": 4,
             "align": "end", "weight": "bold"}
        ]
    }

def _separator():
    return {"type": "separator", "color": "#f5f5f5"}

def _action_bar(text, bg_color):
    """底部動作色塊"""
    return {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": bg_color,
        "paddingAll": "10px",
        "contents": [
            {"type": "text", "text": text, "color": C_WHITE,
             "align": "center", "weight": "bold", "size": "sm"}
        ]
    }

def flex_limit_up(name, code, group, pct, count, has_momentum, peers, now_str):
    """🚀 漲停通知"""
    peer_rows = []
    for pname, pcode, ppct, is_lu in peers[:6]:
        lu_tag = " 🔴" if is_lu else ""
        color = C_RED if ppct >= 3.0 else C_LABEL
        peer_rows.append(_separator())
        peer_rows.append(_row(f"{pname} {pcode}", f"+{ppct:.1f}%{lu_tag}", color))

    momentum = "今日資金進駐 ✅" if has_momentum else "今日資金進駐 ❌"

    return {
        "type": "flex",
        "altText": f"🚀 漲停通知｜{group}｜{name} {code}",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "0px",
                "contents": [
                    # Header
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": C_WINE,
                        "paddingAll": "14px",
                        "contents": [
                            {"type": "text",
                             "text": f"🚀 漲停通知　第 {count} 支",
                             "color": "#ffffff99", "size": "xs", "weight": "bold",
                             "align": "center"},
                            {"type": "text",
                             "text": f"{name} {code}",
                             "color": C_WHITE, "size": "xl", "weight": "bold",
                             "align": "center", "margin": "sm"},
                            {"type": "text",
                             "text": f"{group}　{momentum}",
                             "color": "#ffffff99", "size": "xs",
                             "align": "center", "margin": "sm"},
                        ]
                    },
                    # 同族群列表
                    {
                        "type": "box",
                        "layout": "vertical",
                        "paddingAll": "12px",
                        "contents": [
                            {"type": "text", "text": "同族群漲幅", "color": C_LABEL,
                             "size": "xs", "margin": "none"},
                            *peer_rows
                        ] if peers else [
                            {"type": "text", "text": "同族群無 3% 以上個股",
                             "color": C_LABEL, "size": "xs", "align": "center"}
                        ]
                    },
                    # Footer 時間
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "backgroundColor": "#fafafa",
                        "paddingAll": "8px",
                        "contents": [
                            {"type": "text", "text": "時間", "color": C_LABEL, "size": "xs"},
                            {"type": "text", "text": now_str, "color": C_LABEL,
                             "size": "xs", "align": "end"}
                        ]
                    }
                ]
            }
        }
    }

def flex_fire(name, code, group, start_pct, fire_pct, now_str):
    """🔥 確認突破（族群）"""
    remaining = round(9.0 - fire_pct, 2)
    return {
        "type": "flex",
        "altText": f"🔥 確認突破｜{name} {code} +{fire_pct:.2f}%",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "0px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": C_RED,
                        "paddingAll": "14px",
                        "contents": [
                            {"type": "text",
                             "text": "🔥 確認突破　⚠️ 考驗通過",
                             "color": "#ffffff99", "size": "xs", "weight": "bold",
                             "align": "center"},
                            {"type": "text",
                             "text": f"{name} {code}",
                             "color": C_WHITE, "size": "xl", "weight": "bold",
                             "align": "center", "margin": "sm"},
                            {"type": "text",
                             "text": group,
                             "color": "#ffffff99", "size": "xs",
                             "align": "center", "margin": "sm"},
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "paddingAll": "12px",
                        "contents": [
                            _row("起始點", f"+{start_pct:.1f}%"),
                            _separator(),
                            _row("突破點", f"+{fire_pct:.2f}%", C_RED),
                            _separator(),
                            _row("剩餘空間", f"+{remaining:.2f}%"),
                            _separator(),
                            _row("時間", now_str),
                        ]
                    },
                    _action_bar("▲ 買進", C_RED)
                ]
            }
        }
    }

def flex_trail(name, code, group, fire_pct, peak_pct, trail_pct, cur_pct):
    """⚠️ 移動停利（族群）"""
    now_str = now_taipei().strftime("%H:%M")
    return {
        "type": "flex",
        "altText": f"⚠️ 移動停利｜{name} {code}　建議出場！",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "0px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": C_GREEN,
                        "paddingAll": "14px",
                        "contents": [
                            {"type": "text",
                             "text": "⚠️ 移動停利　建議出場",
                             "color": "#ffffff99", "size": "xs", "weight": "bold",
                             "align": "center"},
                            {"type": "text",
                             "text": f"{name} {code}",
                             "color": C_WHITE, "size": "xl", "weight": "bold",
                             "align": "center", "margin": "sm"},
                            {"type": "text",
                             "text": group,
                             "color": "#ffffff99", "size": "xs",
                             "align": "center", "margin": "sm"},
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "paddingAll": "12px",
                        "contents": [
                            _row("進場點", f"🔥 +{fire_pct:.2f}%"),
                            _separator(),
                            _row("最高點", f"+{peak_pct:.2f}%"),
                            _separator(),
                            _row("停利觸發", f"+{trail_pct:.2f}%", C_GREEN),
                            _separator(),
                            _row("現在", f"+{cur_pct:.2f}%", C_GREEN),
                        ]
                    },
                    _action_bar("▼ 出場", C_GREEN)
                ]
            }
        }
    }

def flex_golden_fire(name, code, start_pct, fire_pct, now_str):
    """⭐ 黃金奇點 確認突破"""
    remaining = round(9.0 - fire_pct, 2)
    return {
        "type": "flex",
        "altText": f"⭐ 黃金奇點｜確認突破｜{name} {code} +{fire_pct:.2f}%",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "0px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": C_WHITE,
                        "paddingAll": "14px",
                        "borderWidth": "0px",
                        "contents": [
                            {"type": "text",
                             "text": "⭐ 黃金奇點",
                             "color": C_GOLD, "size": "lg", "weight": "bold",
                             "align": "center"},
                            {"type": "text",
                             "text": "確認突破　⚠️ 考驗通過",
                             "color": C_RED, "size": "xs", "weight": "bold",
                             "align": "center", "margin": "sm"},
                            {"type": "text",
                             "text": f"{name} {code}",
                             "color": C_RED, "size": "xl", "weight": "bold",
                             "align": "center", "margin": "sm"},
                        ]
                    },
                    {"type": "separator", "color": C_BORDER},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "paddingAll": "12px",
                        "contents": [
                            _row("起始點", f"+{start_pct:.1f}%"),
                            _separator(),
                            _row("突破點", f"+{fire_pct:.2f}%", C_RED),
                            _separator(),
                            _row("剩餘空間", f"+{remaining:.2f}%"),
                            _separator(),
                            _row("時間", now_str),
                        ]
                    },
                    _action_bar("▲ 買進", C_RED)
                ]
            }
        }
    }

def flex_golden_trail(name, code, fire_pct, peak_pct, trail_pct, cur_pct):
    """⭐ 黃金奇點 移動停利"""
    now_str = now_taipei().strftime("%H:%M")
    return {
        "type": "flex",
        "altText": f"⭐ 黃金奇點｜移動停利｜{name} {code}　建議出場！",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "0px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": C_WHITE,
                        "paddingAll": "14px",
                        "contents": [
                            {"type": "text",
                             "text": "⭐ 黃金奇點",
                             "color": C_GOLD, "size": "lg", "weight": "bold",
                             "align": "center"},
                            {"type": "text",
                             "text": "移動停利　建議出場",
                             "color": C_GREEN, "size": "xs", "weight": "bold",
                             "align": "center", "margin": "sm"},
                            {"type": "text",
                             "text": f"{name} {code}",
                             "color": C_GREEN, "size": "xl", "weight": "bold",
                             "align": "center", "margin": "sm"},
                        ]
                    },
                    {"type": "separator", "color": C_BORDER},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "paddingAll": "12px",
                        "contents": [
                            _row("進場點", f"🔥 +{fire_pct:.2f}%"),
                            _separator(),
                            _row("最高點", f"+{peak_pct:.2f}%"),
                            _separator(),
                            _row("停利觸發", f"+{trail_pct:.2f}%", C_GREEN),
                            _separator(),
                            _row("現在", f"+{cur_pct:.2f}%", C_GREEN),
                        ]
                    },
                    _action_bar("▼ 出場", C_GREEN)
                ]
            }
        }
    }

def _closing_detail_bubble(records_chunk, page, total_pages, date_str):
    """收盤統計明細卡（每5隻一張）"""
    rows = []
    for r in records_chunk:
        # 成功：有停利觸發 OR 收盤 >= 進場點（沒賠就算成功）
        is_win = (
            r.get("trail_pct") is not None or
            (r.get("close_pct") is not None and r["close_pct"] >= r["fire_pct"]) or
            (r.get("high_pct") is not None and r["high_pct"] >= 9.0)
        )
        win = "✅" if is_win else "❌"
        fire = f"+{r['fire_pct']:.2f}%"
        high = f"+{r['high_pct']:.1f}%" if r.get("high_pct") else "?"
        src = "⭐" if r.get("source") == "golden" else "🔥"
        rows.append(_separator())
        rows.append({
            "type": "box",
            "layout": "horizontal",
            "paddingTop": "6px",
            "paddingBottom": "6px",
            "contents": [
                {"type": "text",
                 "text": f"{win} {src} {r['name']} {r['code']}",
                 "size": "xs", "color": C_TEXT, "flex": 5},
                {"type": "text",
                 "text": f"{fire}→{high}",
                 "size": "xs", "color": C_LABEL, "flex": 3, "align": "end"}
            ]
        })
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "0px",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": C_WINE,
                    "paddingAll": "14px",
                    "contents": [
                        {"type": "text",
                         "text": f"📊 個股明細　{page}/{total_pages}",
                         "color": "#ffffff99", "size": "xs", "weight": "bold",
                         "align": "center"},
                        {"type": "text",
                         "text": date_str,
                         "color": C_WHITE, "size": "lg", "weight": "bold",
                         "align": "center", "margin": "sm"},
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "paddingAll": "12px",
                    "contents": rows
                }
            ]
        }
    }

def flex_noon(holdings, now_str):
    """🕛 12:00 停利提醒 Flex"""
    rows = []
    for name, code, cur_pct, fire_pct in holdings:
        gain = cur_pct - fire_pct
        color = C_RED if cur_pct >= fire_pct else "#e97316"
        rows.append(_separator())
        rows.append({
            "type": "box",
            "layout": "horizontal",
            "paddingTop": "6px",
            "paddingBottom": "6px",
            "contents": [
                {"type": "text",
                 "text": f"{name} {code}",
                 "size": "sm", "color": C_TEXT, "flex": 4, "weight": "bold"},
                {"type": "text",
                 "text": f"+{cur_pct:.2f}%",
                 "size": "sm", "color": color, "flex": 3,
                 "align": "end", "weight": "bold"},
                {"type": "text",
                 "text": f"進場+{fire_pct:.2f}%",
                 "size": "xs", "color": C_LABEL, "flex": 3, "align": "end"},
            ]
        })
    return {
        "type": "flex",
        "altText": f"🕛 12:00 停利提醒｜持有 {len(holdings)} 隻",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "0px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#e97316",
                        "paddingAll": "14px",
                        "contents": [
                            {"type": "text",
                             "text": "🕛 12:00 停利提醒",
                             "color": "#ffffff99", "size": "xs",
                             "weight": "bold", "align": "center"},
                            {"type": "text",
                             "text": f"持有 {len(holdings)} 隻　建議評估出場",
                             "color": C_WHITE, "size": "lg",
                             "weight": "bold", "align": "center", "margin": "sm"},
                            {"type": "text",
                             "text": now_str,
                             "color": "#ffffff99", "size": "xs", "align": "center",
                             "margin": "sm"},
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "paddingAll": "12px",
                        "contents": rows
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#e9731620",
                        "paddingAll": "10px",
                        "contents": [
                            {"type": "text",
                             "text": "日內交易稅減半，今日結算",
                             "color": "#e97316", "size": "xs", "align": "center"}
                        ]
                    }
                ]
            }
        }
    }

def do_noon_alert(stock_data):
    """12:00 整點：記錄 noon_pct，發停利提醒"""
    now_str = now_taipei().strftime("%H:%M")
    all_records = daily_records + golden_records

    # 更新所有記錄的 noon_pct
    for r in all_records:
        if r.get("noon_pct") is None and r["code"] in stock_data:
            r["noon_pct"] = stock_data[r["code"]]["pct"]

    # 找出仍持有（已🔥但未停利）的股票
    holdings = []
    fired_codes = {r["code"] for r in all_records if r.get("fire_pct")}

    for code in fired_codes:
        # 族群 tracking
        if code in tracking and tracking[code].get("fired"):
            t = tracking[code]
            if code in stock_data:
                holdings.append((
                    t["name"], code,
                    stock_data[code]["pct"],
                    t["fire_pct"]
                ))
        # 黃金奇點 tracking
        elif code in golden_tracking and golden_tracking[code].get("fired"):
            t = golden_tracking[code]
            if code in stock_data:
                holdings.append((
                    t["name"], code,
                    stock_data[code]["pct"],
                    t["fire_pct"]
                ))

    if holdings:
        holdings.sort(key=lambda x: x[2], reverse=True)
        flex = flex_noon(holdings, now_str)
        send_flex(flex)
        print(f"🕛 12:00 停利提醒，{len(holdings)} 隻", flush=True)
    else:
        print("🕛 12:00 無持有部位", flush=True)

def flex_closing(date_str, fired, won, trailed, records):
    """📊 收盤統計 Carousel（第1張總覽 + 每5隻一張明細）"""
    win_rate = f"{len(won)}/{len(fired)} = {len(won)/len(fired)*100:.0f}%" if fired else "—"

    # 第1張：總覽
    group_fired  = [r for r in fired if r.get("source") != "golden"]
    golden_fired = [r for r in fired if r.get("source") == "golden"]
    overview_bubble = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "0px",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": C_WINE,
                    "paddingAll": "14px",
                    "contents": [
                        {"type": "text",
                         "text": "📊 收盤統計",
                         "color": "#ffffff99", "size": "xs", "weight": "bold",
                         "align": "center"},
                        {"type": "text",
                         "text": date_str,
                         "color": C_WHITE, "size": "xl", "weight": "bold",
                         "align": "center", "margin": "sm"},
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "paddingAll": "12px",
                    "contents": [
                        _row("🔥 族群訊號", f"{len(group_fired)} 隻"),
                        _separator(),
                        _row("⭐ 黃金奇點", f"{len(golden_fired)} 隻"),
                        _separator(),
                        _row("訊號合計", f"{len(fired)} 隻"),
                        _separator(),
                        _row("勝率（達 9%）", win_rate, C_RED),
                        _separator(),
                        _row("移動停利觸發", f"{len(trailed)} 隻"),
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "paddingAll": "10px",
                    "paddingTop": "0px",
                    "contents": [
                        {"type": "text",
                         "text": "← 左滑看個股明細",
                         "color": C_LABEL, "size": "xs", "align": "center"}
                    ]
                }
            ]
        }
    }

    # 後續張：每5隻一張
    CHUNK = 5
    chunks = [records[i:i+CHUNK] for i in range(0, len(records), CHUNK)]
    total_pages = len(chunks)
    detail_bubbles = [
        _closing_detail_bubble(chunk, i+1, total_pages, date_str)
        for i, chunk in enumerate(chunks)
    ]

    # 組 Carousel（最多12張）
    all_bubbles = [overview_bubble] + detail_bubbles
    all_bubbles = all_bubbles[:12]

    return {
        "type": "flex",
        "altText": f"📊 收盤統計｜{date_str}　{len(fired)}隻 勝率{win_rate}",
        "contents": {
            "type": "carousel",
            "contents": all_bubbles
        }
    }

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
        "spark_count": 0,
        "had_pullback": False,
        "pullback_low": None,
        "fire_pct": None,
        "fired": False,
        "notified_fire": False,  # 是否發過🔥通知（才追蹤停利）
        "peak_pct": None,
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
                if TRACK_MIN_PCT <= other_pct and other_code not in tracking and can_add_new_tracking():
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

    # 發漲停通知（Flex）
    group_stocks_lines.sort(key=lambda x: x[2], reverse=True)
    peers = [(n, c, p, is_lu) for c, n, p, is_lu in group_stocks_lines]
    flex = flex_limit_up(name, code, group, pct, count, has_momentum, peers, now_str)
    send_flex(flex)
    print(f"🚀 {group} 第{count}支 {name} {code} +{pct:.1f}%", flush=True)

def send_pending_fire():
    """發送批次🔥訊號（每隻獨立一張 Flex 卡片）"""
    global pending_fire
    if not pending_fire:
        return

    now = now_taipei()
    now_str = now.strftime("%H:%M")

    for item in pending_fire:
        flex = flex_fire(
            item['name'], item['code'], item['group'],
            item['start_pct'], item['fire_pct'], now_str
        )
        send_flex(flex)
        print(f"🔥 {item['name']} {item['code']} +{item['fire_pct']:.2f}%", flush=True)

        # 記錄
        daily_records.append({
            "code": item['code'],
            "name": item['name'],
            "group": item['group'],
            "source": "group",
            "start_pct": item['start_pct'],
            "fire_pct": item['fire_pct'],
            "fire_type": item['type'],
            "fire_time": now_str,
            "signals": item['signals'],
            "peak_pct": None,
            "trail_pct": None,
            "noon_pct": None,
            "close_pct": None,
        })

    pending_fire = []

def process_tracking(stock_data):
    """處理追蹤中的股票 v6"""
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
        had_pullback = t["had_pullback"]
        fired = t["fired"]
        notified_fire = t.get("notified_fire", False)
        peak_pct = t["peak_pct"]
        fire_pct = t["fire_pct"]
        is_high_start = start_pct >= 5.0  # 起始5%以上，用不同邏輯

        # ===== 🔥後：追蹤移動停利 =====
        if fired:
            if pct > (peak_pct or 0):
                tracking[code]["peak_pct"] = pct
                peak_pct = pct

            if peak_pct is not None:
                trail_threshold = round(peak_pct * TRAIL_RATIO, 2)
                if pct <= trail_threshold:
                    # 只有notified_fire才發LINE通知
                    if notified_fire:
                        flex = flex_trail(name, code, group, fire_pct,
                                          peak_pct, trail_threshold, pct)
                        send_flex(flex)
                        print(f"⚠️ 移動停利 {name} {code} 現在+{pct:.2f}%", flush=True)

                        # 更新記錄
                        for r in daily_records:
                            if r["code"] == code and r["trail_pct"] is None:
                                r["peak_pct"] = peak_pct
                                r["trail_pct"] = pct
                                break

                    # 不移除tracking！重設狀態等待下次🔥(B)
                    tracking[code]["fired"] = False
                    tracking[code]["fire_pct"] = None
                    tracking[code]["peak_pct"] = None
                    tracking[code]["notified_fire"] = False
                    tracking[code]["had_pullback"] = True  # 保留，視為已有回落
                    # spark_pct / start_pct 不變
                    print(f"↩️ 重設tracking {name} {code}，等待下次進場", flush=True)
            continue

        # ===== 還沒🔥：分兩條路線 =====

        if is_high_start:
            # ===== 起始5%以上：等回落→回起始×1.05 → 🔥(B) =====
            warn_threshold = round(start_pct * WARN_RATIO, 2)
            fire_threshold = round(start_pct * 1.05, 2)

            if not had_pullback:
                if pct <= warn_threshold:
                    tracking[code]["had_pullback"] = True
                    tracking[code]["pullback_low"] = pct
                    print(f"⚠️高起始回落 {name} {code} +{pct:.2f}%，等反彈到{fire_threshold:.2f}%", flush=True)
                # 沒回落前不動作
            else:
                if t.get("pullback_low") and pct < t["pullback_low"]:
                    tracking[code]["pullback_low"] = pct

                if pct >= fire_threshold and pct < 9.5:
                    # 🔥(B)觸發
                    notified = pct <= FIRE_MAX_PCT
                    tracking[code]["fire_pct"] = pct
                    tracking[code]["fired"] = True
                    tracking[code]["peak_pct"] = pct
                    tracking[code]["notified_fire"] = notified

                    if notified:
                        if code not in golden_tracking:
                            fire_batch.append({
                                "code": code, "name": name, "group": group,
                                "start_pct": start_pct, "fire_pct": pct,
                                "type": "HIGH",
                                "signals": "▶→⚠️→🔥"
                            })
                        else:
                            print(f"⭐黃金奇點優先，族群跳過 {name} {code}", flush=True)
                    print(f"🔥高起始 {name} {code} +{pct:.2f}% {'✅通知' if notified else '❌靜默'}", flush=True)

        elif 4.6 <= start_pct < 5.0:
            # ===== 起始4.6~4.9%：⚡×1.25 → 回落 → 反彈回⚡點 → 🔥 =====
            spark_pct = t["spark_pct"]

            if spark_pct is None:
                if not can_add_new_tracking():
                    continue
                threshold = round(start_pct * FIRST_MULT, 2)
                if pct >= threshold:
                    tracking[code]["spark_count"] = t.get("spark_count", 0) + 1
                    if tracking[code]["spark_count"] >= 2:
                        tracking[code]["spark_pct"] = pct
                        tracking[code]["spark_count"] = 0
                        print(f"⚡(中) {name} {code} +{pct:.2f}%", flush=True)
                else:
                    tracking[code]["spark_count"] = 0
            else:
                warn_threshold = round(spark_pct * WARN_RATIO, 2)
                if not had_pullback:
                    if pct <= warn_threshold:
                        tracking[code]["had_pullback"] = True
                        tracking[code]["pullback_low"] = pct
                        print(f"⚠️中段回落 {name} {code} +{pct:.2f}%", flush=True)
                else:
                    if t.get("pullback_low") and pct < t["pullback_low"]:
                        tracking[code]["pullback_low"] = pct
                    if pct >= spark_pct and pct < 9.5:
                        notified = pct <= FIRE_MAX_PCT
                        tracking[code]["fire_pct"] = pct
                        tracking[code]["fired"] = True
                        tracking[code]["peak_pct"] = pct
                        tracking[code]["notified_fire"] = notified
                        if notified:
                            if code not in golden_tracking:
                                fire_batch.append({
                                    "code": code, "name": name, "group": group,
                                    "start_pct": start_pct, "fire_pct": pct,
                                    "type": "MID",
                                    "signals": "▶→⚡→⚠️→🔥"
                                })
                            else:
                                print(f"⭐黃金奇點優先，族群跳過 {name} {code}", flush=True)
                        print(f"🔥(中) {name} {code} +{pct:.2f}% {'✅通知' if notified else '❌靜默'}", flush=True)

        else:
            # ===== 起始3~4.5%：⚡×1.25 → 回落 → 反彈到⚡×1.118 → 🔥 =====
            spark_pct = t["spark_pct"]

            if spark_pct is None:
                if not can_add_new_tracking():
                    continue
                threshold = round(start_pct * FIRST_MULT, 2)
                if pct >= threshold:
                    tracking[code]["spark_count"] = t.get("spark_count", 0) + 1
                    if tracking[code]["spark_count"] >= 2:
                        tracking[code]["spark_pct"] = pct
                        tracking[code]["spark_count"] = 0
                        print(f"⚡ {name} {code} +{pct:.2f}%", flush=True)
                else:
                    tracking[code]["spark_count"] = 0
            else:
                warn_threshold = round(spark_pct * WARN_RATIO, 2)
                fire_threshold = round(spark_pct * SECOND_MULT, 2)

                if not had_pullback:
                    if pct <= warn_threshold:
                        tracking[code]["had_pullback"] = True
                        tracking[code]["pullback_low"] = pct
                        print(f"⚠️內部回落 {name} {code} +{pct:.2f}%", flush=True)
                else:
                    if t.get("pullback_low") and pct < t["pullback_low"]:
                        tracking[code]["pullback_low"] = pct
                    if pct >= fire_threshold and pct < 9.5:
                        notified = pct <= FIRE_MAX_PCT
                        tracking[code]["fire_pct"] = pct
                        tracking[code]["fired"] = True
                        tracking[code]["peak_pct"] = pct
                        tracking[code]["notified_fire"] = notified
                        if notified:
                            if code not in golden_tracking:
                                fire_batch.append({
                                    "code": code, "name": name, "group": group,
                                    "start_pct": start_pct, "fire_pct": pct,
                                    "type": "LOW",
                                    "signals": "▶→⚡→⚠️→🔥×1.118"
                                })
                            else:
                                print(f"⭐黃金奇點優先，族群跳過 {name} {code}", flush=True)
                        print(f"🔥(低) {name} {code} +{pct:.2f}% {'✅通知' if notified else '❌靜默'}", flush=True)

    # 發批次🔥通知
    if fire_batch:
        pending_fire = fire_batch
        send_pending_fire()

def get_last_trading_date():
    """取得最近一個交易日（週一往前推到週五）"""
    import datetime as dt
    now = now_taipei()
    d = now.date()
    if now.hour < 14:
        d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d

# 黃金奇點排除產業
GOLDEN_EXCLUDE_INDUSTRIES = {
    "金融保險", "金融業", "銀行業", "證券", "保險",
    "觀光餐旅", "觀光事業",
    "貿易百貨", "百貨",
    "建材營造", "建設",
    "食品工業", "食品",
    "造紙工業", "造紙",
    "文化創意業", "文化創意",
    "生技醫療", "生物科技",
    "航運業", "航運",
}

def update_golden_codes():
    """用 FinMind 抓前一交易日收盤價+產業，篩選101~130元，排除特定產業"""
    global golden_codes, golden_update_date
    now = now_taipei()
    today_str = now.strftime("%Y-%m-%d")
    if golden_update_date == today_str:
        return

    print("⭐ 更新黃金奇點清單（FinMind）...", flush=True)

    last_trade = get_last_trading_date()
    date_str = last_trade.strftime("%Y-%m-%d")
    print(f"⭐ 使用交易日：{date_str}", flush=True)

    # Step 1：抓股票基本資料（名稱+產業）
    stock_info = {}
    try:
        res = requests.get("https://api.finmindtrade.com/api/v4/data",
            params={"dataset": "TaiwanStockInfo", "token": FINMIND_TOKEN},
            timeout=30)
        data = res.json()
        if data.get("status") == 200:
            for row in data.get("data", []):
                code = str(row.get("stock_id", "")).strip()
                if not code.isdigit() or len(code) != 4:
                    continue
                stock_info[code] = {
                    "name": row.get("stock_name", code),
                    "industry": row.get("industry_category", ""),
                }
            print(f"⭐ 股票基本資料：{len(stock_info)}隻", flush=True)
        else:
            print(f"⭐ TaiwanStockInfo 失敗：{data.get('msg')}", flush=True)
    except Exception as e:
        print(f"⭐ TaiwanStockInfo 錯誤：{e}", flush=True)

    # Step 2：抓收盤價，篩選 101~130，排除產業
    all_found = {}
    try:
        res = requests.get("https://api.finmindtrade.com/api/v4/data",
            params={
                "dataset": "TaiwanStockPrice",
                "start_date": date_str,
                "end_date": date_str,
                "token": FINMIND_TOKEN,
            }, timeout=30)
        data = res.json()

        if data.get("status") != 200:
            print(f"⭐ TaiwanStockPrice 失敗：{data.get('msg')}", flush=True)
            return None

        records = data.get("data", [])
        print(f"⭐ 收盤價共 {len(records)} 筆", flush=True)

        for row in records:
            try:
                code = str(row.get("stock_id", "")).strip()
                # 只保留 4 位純數字（排除 ETF、特殊商品）
                if not code.isdigit() or len(code) != 4:
                    continue
                close = float(row.get("close", 0))
                if not (101 <= close <= 130):
                    continue
                # 流動性篩選：成交量 >= 4000張
                volume = float(row.get("Trading_Volume", 0)) / 1000
                if volume < 4000:
                    continue
                # 排除特定產業
                industry = stock_info.get(code, {}).get("industry", "")
                if any(ex in industry for ex in GOLDEN_EXCLUDE_INDUSTRIES):
                    continue
                name = stock_info.get(code, {}).get("name", code)
                all_found[code] = {"name": name, "close": close}
            except:
                continue

        print(f"⭐ 篩選完成：{len(all_found)}隻（101~130元，已排除特定產業）", flush=True)

    except Exception as e:
        print(f"⭐ TaiwanStockPrice 錯誤：{e}", flush=True)

    if not all_found:
        print("⭐ 黃金奇點更新失敗：沒有抓到任何資料", flush=True)
        return None

    # 補充名稱到 STOCK_TO_NAME
    for code, info in all_found.items():
        if code not in STOCK_TO_NAME or not STOCK_TO_NAME[code]:
            STOCK_TO_NAME[code] = info["name"]

    golden_codes = set(all_found.keys())
    golden_update_date = today_str
    print(f"⭐ 黃金奇點更新完成：共{len(golden_codes)}隻", flush=True)
    return all_found
def add_to_golden_tracking(code, name, start_pct):
    """加入黃金奇點追蹤"""
    if code in golden_tracking:
        return
    golden_tracking[code] = {
        "name": name,
        "start_pct": start_pct,
        "spark_pct": None,
        "spark_count": 0,
        "had_pullback": False,
        "pullback_low": None,
        "fire_pct": None,
        "fired": False,
        "notified_fire": False,
        "peak_pct": None,
    }
    print(f"⭐加入黃金奇點追蹤 {name} {code} 起始+{start_pct:.2f}%", flush=True)

def send_golden_fire(items):
    """發送黃金奇點確認突破（每隻獨立一張 Flex）"""
    now_str = now_taipei().strftime("%H:%M")
    for item in items:
        flex = flex_golden_fire(
            item['name'], item['code'],
            item['start_pct'], item['fire_pct'], now_str
        )
        send_flex(flex)
        print(f"⭐🔥 {item['name']} {item['code']} +{item['fire_pct']:.2f}%", flush=True)
        golden_records.append({
            "code": item['code'],
            "name": item['name'],
            "source": "golden",
            "start_pct": item['start_pct'],
            "fire_pct": item['fire_pct'],
            "fire_time": now_str,
            "peak_pct": None,
            "trail_pct": None,
            "noon_pct": None,
            "close_pct": None,
        })

def process_golden_tracking(stock_data):
    """處理黃金奇點追蹤（邏輯與process_tracking相同）"""
    fire_batch = []

    for code, t in list(golden_tracking.items()):
        if code not in stock_data:
            continue

        info = stock_data[code]
        pct = info["pct"]
        name = info["name"] or t["name"]

        # 漲停 → 移除
        if info["is_limit_up"]:
            del golden_tracking[code]
            continue

        start_pct = t["start_pct"]
        had_pullback = t["had_pullback"]
        fired = t["fired"]
        notified_fire = t.get("notified_fire", False)
        peak_pct = t["peak_pct"]
        fire_pct = t["fire_pct"]
        is_high_start = start_pct >= 5.0

        # 🔥後：追蹤移動停利
        if fired:
            if pct > (peak_pct or 0):
                golden_tracking[code]["peak_pct"] = pct
                peak_pct = pct

            if peak_pct is not None:
                trail_threshold = round(peak_pct * TRAIL_RATIO, 2)
                if pct <= trail_threshold:
                    if notified_fire:
                        flex = flex_golden_trail(name, code, fire_pct,
                                                  peak_pct, trail_threshold, pct)
                        send_flex(flex)
                        print(f"⭐⚠️ 移動停利 {name} {code} 現在+{pct:.2f}%", flush=True)
                        for r in golden_records:
                            if r["code"] == code and r["trail_pct"] is None:
                                r["peak_pct"] = peak_pct
                                r["trail_pct"] = pct
                                break

                    # 重設狀態等待下次進場
                    golden_tracking[code]["fired"] = False
                    golden_tracking[code]["fire_pct"] = None
                    golden_tracking[code]["peak_pct"] = None
                    golden_tracking[code]["notified_fire"] = False
                    golden_tracking[code]["had_pullback"] = True
            continue

        # 還沒🔥
        if is_high_start:
            # 起始5%以上：等回落→回起始×1.05
            warn_threshold = round(start_pct * WARN_RATIO, 2)
            fire_threshold = round(start_pct * 1.05, 2)

            if not had_pullback:
                if pct <= warn_threshold:
                    golden_tracking[code]["had_pullback"] = True
                    golden_tracking[code]["pullback_low"] = pct
            else:
                if t.get("pullback_low") and pct < t["pullback_low"]:
                    golden_tracking[code]["pullback_low"] = pct
                if pct >= fire_threshold and pct < 9.5:
                    notified = pct <= FIRE_MAX_PCT
                    golden_tracking[code]["fire_pct"] = pct
                    golden_tracking[code]["fired"] = True
                    golden_tracking[code]["peak_pct"] = pct
                    golden_tracking[code]["notified_fire"] = notified
                    if notified:
                        fire_batch.append({"code": code, "name": name,
                            "start_pct": start_pct, "fire_pct": pct})
        elif 4.6 <= start_pct < 5.0:
            # 起始4.6~4.9%：⚡×1.25→⚠️→反彈回⚡點
            spark_pct = t["spark_pct"]

            if spark_pct is None:
                if not can_add_new_tracking():
                    continue
                threshold = round(start_pct * FIRST_MULT, 2)
                if pct >= threshold:
                    golden_tracking[code]["spark_count"] = t.get("spark_count", 0) + 1
                    if golden_tracking[code]["spark_count"] >= 2:
                        golden_tracking[code]["spark_pct"] = pct
                        golden_tracking[code]["spark_count"] = 0
                        print(f"⭐⚡(中) {name} {code} +{pct:.2f}%", flush=True)
                else:
                    golden_tracking[code]["spark_count"] = 0
            else:
                warn_threshold = round(spark_pct * WARN_RATIO, 2)
                if not had_pullback:
                    if pct <= warn_threshold:
                        golden_tracking[code]["had_pullback"] = True
                        golden_tracking[code]["pullback_low"] = pct
                else:
                    if t.get("pullback_low") and pct < t["pullback_low"]:
                        golden_tracking[code]["pullback_low"] = pct
                    if pct >= spark_pct and pct < 9.5:
                        notified = pct <= FIRE_MAX_PCT
                        golden_tracking[code]["fire_pct"] = pct
                        golden_tracking[code]["fired"] = True
                        golden_tracking[code]["peak_pct"] = pct
                        golden_tracking[code]["notified_fire"] = notified
                        if notified:
                            fire_batch.append({"code": code, "name": name,
                                "start_pct": start_pct, "fire_pct": pct})

        else:
            # 起始3~4.5%：⚡×1.25→⚠️→反彈到⚡×1.118
            spark_pct = t["spark_pct"]

            if spark_pct is None:
                if not can_add_new_tracking():
                    continue
                threshold = round(start_pct * FIRST_MULT, 2)
                if pct >= threshold:
                    golden_tracking[code]["spark_count"] = t.get("spark_count", 0) + 1
                    if golden_tracking[code]["spark_count"] >= 2:
                        golden_tracking[code]["spark_pct"] = pct
                        golden_tracking[code]["spark_count"] = 0
                        print(f"⭐⚡ {name} {code} +{pct:.2f}%", flush=True)
                else:
                    golden_tracking[code]["spark_count"] = 0
            else:
                warn_threshold = round(spark_pct * WARN_RATIO, 2)
                fire_threshold = round(spark_pct * SECOND_MULT, 2)
                if not had_pullback:
                    if pct <= warn_threshold:
                        golden_tracking[code]["had_pullback"] = True
                        golden_tracking[code]["pullback_low"] = pct
                else:
                    if t.get("pullback_low") and pct < t["pullback_low"]:
                        golden_tracking[code]["pullback_low"] = pct
                    if pct >= fire_threshold and pct < 9.5:
                        notified = pct <= FIRE_MAX_PCT
                        golden_tracking[code]["fire_pct"] = pct
                        golden_tracking[code]["fired"] = True
                        golden_tracking[code]["peak_pct"] = pct
                        golden_tracking[code]["notified_fire"] = notified
                        if notified:
                            fire_batch.append({"code": code, "name": name,
                                "start_pct": start_pct, "fire_pct": pct})

    if fire_batch:
        send_golden_fire(fire_batch)

def do_closing_summary():
    """收盤統計"""
    all_records = daily_records + golden_records
    if not all_records:
        print("今天沒有記錄", flush=True)
        return

    # 抓收盤價
    codes = list(set([r["code"] for r in all_records]))
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

    for r in all_records:
        final = final_data.get(r["code"], {})
        r["high_pct"] = final.get("high_pct")
        r["close_pct"] = final.get("close_pct")

    today_str = now_taipei().strftime("%Y-%m-%d")

    # 族群歷史 push
    history_group = {}
    try:
        res = requests.get("https://raw.githubusercontent.com/ting78963/stock-alert/main/stats.json", timeout=10)
        if res.status_code == 200:
            history_group = res.json()
    except: pass
    history_group[today_str] = daily_records
    push_to_github("stats.json", history_group)

    # 黃金奇點歷史 push
    history_golden = {}
    try:
        res = requests.get("https://raw.githubusercontent.com/ting78963/stock-alert/main/stats_golden.json", timeout=10)
        if res.status_code == 200:
            history_golden = res.json()
    except: pass
    history_golden[today_str] = golden_records
    push_to_github("stats_golden.json", history_golden)

    # 合併計算勝率
    fired = [r for r in all_records if r.get("fire_pct")]
    won = [r for r in fired if (
        r.get("trail_pct") is not None or
        (r.get("close_pct") is not None and r["close_pct"] >= r["fire_pct"]) or
        (r.get("high_pct") is not None and r["high_pct"] >= 9.0)
    )]
    trailed = [r for r in fired if r.get("trail_pct")]

    flex = flex_closing(today_str, fired, won, trailed, fired)
    send_flex(flex)
    print(f"收盤統計完成，族群{len(daily_records)}筆 黃金{len(golden_records)}筆", flush=True)
    daily_records.clear()
    golden_records.clear()

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
        # 收盤後更新黃金奇點清單（為明天準備）
        update_golden_codes()

def check_stocks():
    global golden_snapshot_done, noon_done_date
    now = now_taipei()
    print(f"監控中 {now.strftime('%H:%M:%S')} 交易時間：{is_trading_time()}", flush=True)

    if not is_trading_time():
        notified_limit_up.clear()
        group_limit_up_count.clear()
        group_triggered.clear()
        tracking.clear()
        golden_tracking.clear()
        daily_records.clear()
        golden_records.clear()
        golden_snapshot_done = False
        return

    # 抓所有股票資料（含黃金奇點）
    all_codes = list(set(
        [s for stocks in GROUPS.values() for s in stocks] +
        list(tracking.keys()) +
        list(golden_codes) +
        list(golden_tracking.keys())
    ))
    stock_data = fetch_stocks(all_codes)

    # 處理族群追蹤
    process_tracking(stock_data)

    # 黃金奇點：09:10固定快照一次
    now = now_taipei()
    if now.hour == 9 and now.minute == 0 and not golden_snapshot_done:
        count = 0
        for code in golden_codes:
            if code in golden_tracking or code not in stock_data:
                continue
            pct = stock_data[code]["pct"]
            if pct >= TRACK_MIN_PCT:
                name = stock_data[code]["name"] or STOCK_TO_NAME.get(code, code)
                add_to_golden_tracking(code, name, pct)
                count += 1
        golden_snapshot_done = True
        print(f"⭐ 09:00快照完成！共{count}隻黃金奇點股票加入追蹤", flush=True)
        if count > 0:
            names = [golden_tracking[c]["name"] for c in list(golden_tracking.keys())[:10]]
            print(f"⭐ 追蹤名單：{', '.join(names)}", flush=True)

    # 處理黃金奇點追蹤
    process_golden_tracking(stock_data)

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
            if TRACK_MIN_PCT <= pct and can_add_new_tracking():
                name = stock_data[code]["name"] or STOCK_TO_NAME.get(code, code)
                add_to_tracking(code, name, group, pct)

    # 12:00 停利提醒（stock_data 已抓好，在這裡觸發）
    now2 = now_taipei()
    today_str2 = now2.strftime("%Y-%m-%d")
    if now2.hour == 12 and now2.minute == 0 and noon_done_date != today_str2 and now2.weekday() < 5:
        noon_done_date = today_str2
        do_noon_alert(stock_data)

# ===== Flask路由 =====
@app.route("/golden_test")
def golden_test():
    """強制重跑黃金奇點清單，列出所有抓到的股票"""
    global golden_update_date
    golden_update_date = None  # 強制重跑
    result = update_golden_codes()
    if result is None:
        return "❌ 抓取失敗，請看 Render logs", 500

    # 按股票代號排序輸出
    lines = [f"⭐ 黃金奇點清單（101~130元）共 {len(result)} 隻"]
    lines.append("=" * 30)
    for code in sorted(result.keys()):
        info = result[code]
        name = info["name"] if isinstance(info, dict) else info
        close = info["close"] if isinstance(info, dict) else ""
        lines.append(f"{code}　{name}　${close}")
    return "<br>".join(lines), 200, {"Content-Type": "text/html; charset=utf-8"}
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
    now_str = now_taipei().strftime("%H:%M")

    # 1. 🚀 漲停通知
    send_flex(flex_limit_up(
        "穩懋", "3105", "光通訊", 10.0, 2, True,
        [("聯亞", "3081", 4.2, False), ("上詮", "3363", 3.7, False), ("光聖", "6442", 1.8, False)],
        now_str
    ))
    time.sleep(0.5)

    # 2. 🔥 確認突破
    send_flex(flex_fire("聯亞", "3081", "光通訊", 3.1, 3.92, now_str))
    time.sleep(0.5)

    # 3. ⚠️ 移動停利
    send_flex(flex_trail("臺慶科", "3357", "被動元件", 5.02, 6.28, 5.65, 5.30))
    time.sleep(0.5)

    # 4. ⭐ 黃金奇點 確認突破
    send_flex(flex_golden_fire("台虹", "8039", 3.4, 4.25, now_str))
    time.sleep(0.5)

    # 5. ⭐ 黃金奇點 移動停利
    send_flex(flex_golden_trail("台虹", "8039", 3.92, 5.80, 5.22, 5.10))
    time.sleep(0.5)

    # 6. 🕛 12:00 停利提醒（模擬）
    mock_holdings = [
        ("聯亞", "3081", 5.20, 3.92),
        ("臺慶科", "3357", 4.80, 5.02),
        ("台虹", "8039", 6.10, 4.25),
    ]
    send_flex(flex_noon(mock_holdings, now_str))
    time.sleep(0.5)

    # 7. 📊 收盤統計（模擬 21 隻）
    mock_records = [
        {"code":"3081","name":"聯亞","source":"group","fire_pct":3.92,"high_pct":9.1,"trail_pct":None},
        {"code":"3357","name":"臺慶科","source":"group","fire_pct":5.02,"high_pct":6.8,"trail_pct":5.65},
        {"code":"8039","name":"台虹","source":"golden","fire_pct":4.25,"high_pct":9.3,"trail_pct":None},
        {"code":"6207","name":"雷科","source":"group","fire_pct":4.60,"high_pct":4.1,"trail_pct":None},
        {"code":"3105","name":"穩懋","source":"group","fire_pct":3.55,"high_pct":9.5,"trail_pct":None},
        {"code":"3363","name":"上詮","source":"group","fire_pct":4.10,"high_pct":7.2,"trail_pct":4.80},
        {"code":"6442","name":"光聖","source":"group","fire_pct":3.80,"high_pct":9.2,"trail_pct":None},
        {"code":"2327","name":"國巨","source":"group","fire_pct":3.20,"high_pct":3.5,"trail_pct":None},
        {"code":"3042","name":"晶技","source":"golden","fire_pct":4.50,"high_pct":9.6,"trail_pct":None},
        {"code":"2481","name":"強茂","source":"group","fire_pct":3.70,"high_pct":5.1,"trail_pct":None},
        {"code":"3017","name":"奇鋐","source":"group","fire_pct":3.30,"high_pct":9.0,"trail_pct":None},
        {"code":"3324","name":"雙鴻","source":"group","fire_pct":4.20,"high_pct":6.3,"trail_pct":5.10},
        {"code":"2317","name":"鴻海","source":"group","fire_pct":3.10,"high_pct":4.0,"trail_pct":None},
        {"code":"6669","name":"緯穎","source":"group","fire_pct":5.20,"high_pct":9.8,"trail_pct":None},
        {"code":"3035","name":"智原","source":"group","fire_pct":3.90,"high_pct":9.1,"trail_pct":None},
        {"code":"3661","name":"世芯-KY","source":"golden","fire_pct":4.80,"high_pct":8.5,"trail_pct":None},
        {"code":"6285","name":"啟碁","source":"group","fire_pct":3.40,"high_pct":9.3,"trail_pct":None},
        {"code":"2344","name":"華邦電","source":"group","fire_pct":3.60,"high_pct":3.8,"trail_pct":None},
        {"code":"3037","name":"欣興","source":"group","fire_pct":4.30,"high_pct":9.5,"trail_pct":None},
        {"code":"6239","name":"力成","source":"group","fire_pct":3.75,"high_pct":7.8,"trail_pct":6.20},
        {"code":"2395","name":"研華","source":"golden","fire_pct":4.10,"high_pct":9.2,"trail_pct":None},
    ]
    fired = mock_records
    won = [r for r in fired if (
        r.get("trail_pct") is not None or
        (r.get("close_pct") is not None and r["close_pct"] >= r.get("fire_pct", 0)) or
        (r.get("high_pct") is not None and r["high_pct"] >= 9.0)
    )]
    trailed = [r for r in fired if r.get("trail_pct")]
    send_flex(flex_closing(now_taipei().strftime("%Y-%m-%d"), fired, won, trailed, fired))

    return "✅ 六種測試訊息已發送！", 200

@app.route("/golden")
def golden_status():
    return {
        "golden_codes": len(golden_codes),
        "golden_tracking": len(golden_tracking),
        "sample": list(golden_codes)[:10],
    }
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
        time.sleep(3)

monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
