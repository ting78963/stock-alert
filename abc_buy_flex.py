from __future__ import annotations

C_RED="#dc2626"; C_WHITE="#ffffff"; C_TEXT="#1a1a1a"; C_LABEL="#aaaaaa"

def _row(label,value,value_color=None):
    return {"type":"box","layout":"horizontal","paddingTop":"5px","paddingBottom":"5px","borderWidth":"0px","contents":[
        {"type":"text","text":label,"color":C_LABEL,"size":"sm","flex":3},
        {"type":"text","text":str(value),"color":value_color or C_TEXT,"size":"sm","flex":4,"align":"end","weight":"bold"}]}

def _sep():
    return {"type":"separator","color":"#f5f5f5"}

def abc_buy_flex(event,name=None):
    """Keep the old red buy-signal visual shell; content is exclusively the new A/B/C system."""
    code=str(event.get("stock_id") or event.get("symbol") or "")
    cls=str(event.get("signal_class") or event.get("abc") or "?")
    title=f"{name} {code}".strip() if name else code
    vr=event.get("a2_vr")
    eh=event.get("early_high_pct")
    rec=event.get("recognition_time") or "—"
    known=event.get("live_known_time") or rec
    late=bool(event.get("late_discovery",False))

    vr_s=f"{float(vr):.3f}" if vr is not None else "—"
    eh_s=f"{float(eh):.2f}%" if eh is not None else "—"
    timing="補回後確認" if late else "即時確認"

    return {
      "type":"flex",
      "altText":f"🔥 {cls} 買進訊號｜{title}",
      "contents":{"type":"bubble","body":{"type":"box","layout":"vertical","paddingAll":"0px","contents":[
        {"type":"box","layout":"vertical","backgroundColor":C_RED,"paddingAll":"14px","contents":[
          {"type":"text","text":"🔥 趨勢確認　買進訊號","color":"#ffffff99","size":"xs","weight":"bold","align":"center"},
          {"type":"text","text":title,"color":C_WHITE,"size":"xl","weight":"bold","align":"center","margin":"sm"},
          {"type":"text","text":f"{cls} 型｜Frozen Early","color":"#ffffff99","size":"xs","align":"center","margin":"sm"}]},
        {"type":"box","layout":"vertical","paddingAll":"12px","contents":[
          _row("辨識類型",f"{cls} 型",C_RED),_sep(),
          _row("A2 VR",vr_s),_sep(),
          _row("Early High",eh_s),_sep(),
          _row("Frozen Early",rec),_sep(),
          _row("系統知道時間",known),_sep(),
          _row("辨識狀態",timing)]},
        {"type":"box","layout":"vertical","backgroundColor":C_RED,"paddingAll":"10px","contents":[
          {"type":"text","text":"▲ 買進","color":C_WHITE,"align":"center","weight":"bold","size":"sm"}]}
      ]}}}

def format_buy_text(event,name=None):
    code=str(event.get("stock_id") or event.get("symbol") or "")
    cls=str(event.get("signal_class") or "?")
    title=f"{name} {code}".strip() if name else code
    return f"🔥 {cls} 型買進訊號｜{title}"
