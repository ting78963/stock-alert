from __future__ import annotations
import json
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

TPE=ZoneInfo("Asia/Taipei")
MAX_LIMIT_UP_NOTIFY=3
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

STOCK_TO_GROUP={}
STOCK_TO_NAME={}
for group_name,stocks in GROUPS.items():
    for stock in stocks:
        if stock not in STOCK_TO_GROUP: STOCK_TO_GROUP[stock]=group_name
for group_name,stocks in GROUPS_DISPLAY.items():
    for name,code in stocks: STOCK_TO_NAME[code]=name

_lock=threading.Lock()
_state_date=None
_notified=set()
_group_count={}
_STATE_FILE="/tmp/stock-alert-group-limit-up.json"
_bootstrapped=False

def _save_state():
    try:
        with open(_STATE_FILE,"w",encoding="utf-8") as f:
            json.dump({"date":_state_date,"notified":sorted(_notified),"group_count":_group_count},f,ensure_ascii=False)
    except Exception as e:
        print(f"group-limit-up state save error: {e}",flush=True)

def _load_state_for_today():
    global _state_date,_notified,_group_count
    today=datetime.now(TPE).date().isoformat()
    try:
        with open(_STATE_FILE,"r",encoding="utf-8") as f:
            s=json.load(f)
        if s.get("date")==today:
            _state_date=today
            _notified=set(s.get("notified",[]))
            _group_count={str(k):int(v) for k,v in (s.get("group_count") or {}).items()}
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"group-limit-up state load error: {e}",flush=True)
    return False

def _reset_day_if_needed():
    global _state_date
    d=datetime.now(TPE).date().isoformat()
    with _lock:
        if d!=_state_date:
            _state_date=d; _notified.clear(); _group_count.clear(); _save_state()

def _trading_time():
    n=datetime.now(TPE)
    if n.weekday()>=5:return False
    m=n.hour*60+n.minute
    return 540<=m<=810

def _send_flex(msg,line_token,group_id):
    if not line_token or not group_id:
        print(json.dumps(msg,ensure_ascii=False),flush=True); return False
    r=requests.post("https://api.line.me/v2/bot/message/push",
        headers={"Authorization":f"Bearer {line_token}","Content-Type":"application/json"},
        json={"to":group_id,"messages":[msg]},timeout=10)
    print(f"LINE group-limit-up: {r.status_code}",flush=True)
    return 200<=r.status_code<300

def _row(label,value,color="#1a1a1a"):
    return {"type":"box","layout":"horizontal","paddingTop":"5px","paddingBottom":"5px","contents":[
        {"type":"text","text":label,"color":"#aaaaaa","size":"sm","flex":3},
        {"type":"text","text":value,"color":color,"size":"sm","flex":4,"align":"end","weight":"bold"}]}

def _flex(name,code,group,pct,count,has_momentum,peers,now_str):
    rows=[]
    for pname,pcode,ppct,is_lu in peers[:6]:
        rows += [{"type":"separator","color":"#f5f5f5"},
                 _row(f"{pname} {pcode}",f"+{ppct:.1f}%"+(" 🔴" if is_lu else ""),"#dc2626" if ppct>=3 else "#aaaaaa")]
    momentum="今日資金進駐 ✅" if has_momentum else "今日資金進駐 ❌"
    body=[
      {"type":"box","layout":"vertical","backgroundColor":"#8b1a1a","paddingAll":"14px","contents":[
       {"type":"text","text":f"🚀 漲停通知　第 {count} 支","color":"#ffffff99","size":"xs","weight":"bold","align":"center"},
       {"type":"text","text":f"{name} {code}","color":"#ffffff","size":"xl","weight":"bold","align":"center","margin":"sm"},
       {"type":"text","text":f"{group}　{momentum}","color":"#ffffff99","size":"xs","align":"center","margin":"sm"}]},
      {"type":"box","layout":"vertical","paddingAll":"12px","contents":
       ([{"type":"text","text":"同族群漲幅","color":"#aaaaaa","size":"xs","margin":"none"}]+rows if peers else
        [{"type":"text","text":"同族群無 3% 以上個股","color":"#aaaaaa","size":"xs","align":"center"}])},
      {"type":"box","layout":"horizontal","backgroundColor":"#fafafa","paddingAll":"8px","contents":[
       {"type":"text","text":"時間","color":"#aaaaaa","size":"xs"},
       {"type":"text","text":now_str,"color":"#aaaaaa","size":"xs","align":"end"}]}]
    return {"type":"flex","altText":f"🚀 漲停通知｜{group}｜{name} {code}",
            "contents":{"type":"bubble","body":{"type":"box","layout":"vertical","paddingAll":"0px","contents":body}}}

def _fetch(codes):
    out={}
    for i in range(0,len(codes),25):
        batch=codes[i:i+25]
        ex_ch="|".join([f"tse_{x}.tw|otc_{x}.tw" for x in batch])
        try:
            r=requests.get(f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0",timeout=10)
            r.raise_for_status()
            for item in r.json().get("msgArray",[]):
                code=item.get("c",""); z=item.get("z","-"); y=item.get("y","-")
                if code and z not in ("-","") and y not in ("-","") and float(y)>0:
                    pct=round((float(z)-float(y))/float(y)*100,2)
                    out[code]={"name":item.get("n","") or STOCK_TO_NAME.get(code,code),"pct":pct,"is_limit_up":pct>=9.5}
        except Exception as e: print(f"group-limit-up TWSE error: {e}",flush=True)
        time.sleep(.2)
    return out

def scan_once(line_token,group_id):
    global _bootstrapped,_state_date
    _reset_day_if_needed()
    if not _trading_time(): return
    data=_fetch(list(STOCK_TO_GROUP))

    # Restart/deploy safety: restore today's sent set when possible. If no state
    # exists (e.g. a fresh Render instance), treat stocks already at limit-up
    # as the baseline so a restart cannot resend old limit-up alerts.
    if not _bootstrapped:
        restored=_load_state_for_today()
        if not restored:
            with _lock:
                _state_date=datetime.now(TPE).date().isoformat()
                for code,info in data.items():
                    if info["is_limit_up"]:
                        _notified.add(code)
                        group=STOCK_TO_GROUP.get(code)
                        if group:
                            _group_count[group]=_group_count.get(group,0)+1
                _save_state()
            print(f"group-limit-up bootstrap baseline: {len(_notified)} already-limit-up stocks suppressed",flush=True)
        else:
            print(f"group-limit-up restored dedupe state: {len(_notified)} stocks",flush=True)
        _bootstrapped=True
    for code,info in data.items():
        if not info["is_limit_up"]:continue
        group=STOCK_TO_GROUP.get(code)
        if not group:continue
        with _lock:
            if code in _notified:continue
            _notified.add(code)
            count=_group_count.get(group,0)+1; _group_count[group]=count
            _save_state()
        if count>MAX_LIMIT_UP_NOTIFY:continue
        peers=[]
        for other in GROUPS.get(group,[]):
            if other==code or other not in data:continue
            p=data[other]["pct"]
            if p>=3.0: peers.append((data[other]["name"],other,p,p>=9.5))
        peers.sort(key=lambda x:x[2],reverse=True)
        _send_flex(_flex(info["name"],code,group,info["pct"],count,count>=3,peers,datetime.now(TPE).strftime("%H:%M:%S")),line_token,group_id)
        print(f"🚀 {group} 第{count}支 {info['name']} {code} +{info['pct']:.1f}%",flush=True)

def monitor_loop(line_token,group_id,interval=3):
    while True:
        try: scan_once(line_token,group_id)
        except Exception as e: print(f"group-limit-up monitor error: {e}",flush=True)
        time.sleep(interval)
