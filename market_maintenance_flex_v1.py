# -*- coding: utf-8 -*-
"""Market history maintenance LINE Flex payload only. Never sends LINE or changes scanner."""
from datetime import date

def _status(label, value, detail):
    return {"type":"box","layout":"vertical","spacing":"xs","contents":[
        {"type":"text","text":label,"size":"sm","color":"#A3B3C9"},
        {"type":"text","text":value,"size":"md","weight":"bold","color":"#F3F6FC"},
        {"type":"text","text":detail,"size":"xs","color":"#A3B3C9","wrap":True},
    ]}

def build_market_maintenance_flex(report_date, taiex, fx):
    """Two independent status dicts: {status, latest, count, detail}.

    A result is complete only when the latest record matches report_date.
    No false success on stale/missing/failed data.
    """
    day=date.fromisoformat(str(report_date)[:10]).isoformat()
    def normalize(obj):
        obj=obj if isinstance(obj,dict) else {}
        latest=obj.get("latest")
        status=obj.get("status")
        ready=status in ("updated","already_updated") and latest==day
        detail=obj.get("detail") or ("資料日期："+str(latest) if latest else "尚無可用資料")
        if latest!=day:
            detail+="｜非當日資料"
        return ("完成" if ready else "待補齊",detail,ready)
    ta,td,tok=normalize(taiex)
    fa,fd,fok=normalize(fx)
    all_ok=tok and fok
    return {"type":"flex","altText":f"{day} 市場資料維護"+("完成" if all_ok else "未完成"),
        "contents":{"type":"bubble","size":"mega","body":{
            "type":"box","layout":"vertical","backgroundColor":"#101C2E","paddingAll":"16px","spacing":"lg",
            "contents":[
                {"type":"text","text":"MARKET DATA · DAILY MAINTENANCE","size":"xs","color":"#A3B3C9"},
                {"type":"text","text":"市場資料維護報告","size":"lg","weight":"bold","color":"#F3F6FC"},
                {"type":"text","text":day+"｜"+("全部完成" if all_ok else "部分資料待補齊"),"size":"sm","color":"#63D4A6" if all_ok else "#FFC65A"},
                {"type":"separator","color":"#34465F"},
                _status("加權指數｜日／週 MA20、MA100",ta,td),
                _status("美元／新臺幣｜日 MA5、MA20",fa,fd),
                {"type":"separator","color":"#34465F"},
                {"type":"text","text":"資料驗證報告｜不代表股票辨識系統重新啟動","size":"xs","color":"#A3B3C9","wrap":True},
            ]}}}
