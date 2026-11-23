"""Independent 08:55 SOX premarket LINE report; does not modify the scanner."""
from datetime import datetime
from zoneinfo import ZoneInfo
from research.premarket_sox_brief_section_v1 import build_sox_brief_section

TPE=ZoneInfo("Asia/Taipei")

def build_premarket_sox_flex(now, section_builder=build_sox_brief_section):
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("aware datetime required")
    day=now.astimezone(TPE).date().isoformat()
    return {"type":"flex","altText":f"{day} 08:55 盤前簡報",
        "contents":{"type":"bubble","size":"mega","body":{"type":"box","layout":"vertical",
            "backgroundColor":"#101C2E","paddingAll":"16px","spacing":"lg","contents":[
                {"type":"text","text":"PREMARKET · 08:55","size":"xs","color":"#A3B3C9"},
                {"type":"text","text":"盤前市場簡報","size":"lg","weight":"bold","color":"#F3F6FC"},
                {"type":"text","text":day,"size":"sm","color":"#A3B3C9"},
                {"type":"separator","color":"#34465F"},
                section_builder(day),
            ]}}}
