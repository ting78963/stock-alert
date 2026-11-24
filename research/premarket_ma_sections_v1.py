"""Read-only morning brief sections using the restored trend implementations."""
from taiex_fugle_store_v1 import read_store as read_taiex
from usdtwd_cbc_store_v1 import read_store as read_fx
from research.taiex_premarket_flex_v1 import taiex_trend_flex_box, STATUS, DIRECTION
from research.usdtwd_premarket_trend_v1 import fx_premarket_snapshot

def line(value):
    return {"type":"text","text":value,"color":"#FFFFFF","size":"xs","wrap":True}

def box(title, lines):
    return {"type":"box","layout":"vertical","spacing":"sm","contents":[
        {"type":"text","text":title,"color":"#8BC5FF","weight":"bold","size":"md"},
        *[line(x) for x in lines]]}

def build_ma_sections(day, taiex_reader=read_taiex, fx_reader=read_fx):
    try:
        taiex=taiex_trend_flex_box(taiex_reader(),day)
    except Exception:
        taiex=box("大盤均線趨勢",["資料暫不可用"])
    try:
        fx=fx_premarket_snapshot(fx_reader(),day)
        lines=[]
        for p in (5,20):
            value=fx[f"ma{p}"]
            direction=DIRECTION[fx[f"ma{p}_direction"]]
            lines.append(f"MA{p}：{value:.3f}｜新臺幣方向 {direction}" if value is not None else f"MA{p}：資料不足")
        status=STATUS[fx["ma5_20"]]
        if fx["cross_day"] is not None:
            status+=f" Day{fx['cross_day']}"
        lines.append("新臺幣 5/20："+status)
        lines.append("央行收盤資料："+(fx["last_close_date"] or "資料不足"))
        currency=box("新臺幣均線趨勢",lines)
    except Exception:
        currency=box("新臺幣均線趨勢",["資料暫不可用"])
    return [taiex,currency]
