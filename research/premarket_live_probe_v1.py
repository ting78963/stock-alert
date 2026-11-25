"""Read-only live diagnostics. Run from repository root: python -m research.premarket_live_probe_v1."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from taiex_fugle_store_v1 import read_store as read_taiex
from usdtwd_cbc_store_v1 import read_store as read_cbc
from taiex_trend_narrative_v1 import analyze_taiex
from usdtwd_live_rates_v1 import fetch_once
from research.premarket_sox_quote_adapter_v1 import fetch_sox_quote
from research.premarket_tx_fugle_v1 import fetch_tx_quote

def main():
    now=datetime.now(ZoneInfo("Asia/Taipei"))
    def taiex():
        rows=read_taiex()
        return {"count":len(rows),"last":rows[-1] if rows else None,"trend":analyze_taiex(rows,now.date())}
    def cbc():
        rows=read_cbc()
        return {"count":len(rows),"last":rows[-1] if rows else None}
    results={"observed_at":now.isoformat()}
    for key,fn in (("taiex",taiex),("cbc",cbc),("usdtwd",fetch_once),("sox",lambda:fetch_sox_quote(datetime.now(now.tzinfo))),("tx",lambda:fetch_tx_quote(datetime.now(now.tzinfo)))):
        try:
            value=fn()
            results[key]={"status":"available" if value else "unavailable","data":value}
        except Exception as exc:
            results[key]={"status":"error","error_type":type(exc).__name__}
    print(json.dumps(results,ensure_ascii=False,default=str,indent=2))

if __name__=="__main__":
    main()
