"""Read-only four-market briefing assembly; no LINE or scanner side effects."""
from datetime import datetime
from zoneinfo import ZoneInfo
from premarket_taiex_adapter_v1 import build_taiex_preview
from usdtwd_cbc_store_v1 import read_store
from usdtwd_live_rates_v1 import fetch_once
from research.premarket_sox_quote_adapter_v1 import fetch_sox_quote
from research.premarket_tx_fugle_v1 import fetch_tx_quote

TPE = ZoneInfo("Asia/Taipei")

def build_market_brief(now, fx_fetch=fetch_once, sox_fetch=fetch_sox_quote,
                       tx_fetch=fetch_tx_quote, cbc_read=read_store,
                       preview=build_taiex_preview, clock=None):
    if now.tzinfo is None:
        raise ValueError("aware datetime required")
    local = now.astimezone(TPE)
    # Inject a clock for deterministic tests; production supplies a real clock.
    clock = clock or (lambda: now)
    values = {}
    for key, fetch in (("usdtwd", lambda: fx_fetch()), ("sox", lambda: sox_fetch(clock())),
                       ("tx", lambda: tx_fetch(clock()))):
        try:
            values[key] = fetch()
        except Exception:
            values[key] = None
    try:
        cbc = cbc_read()
    except Exception:
        cbc = []
    card = preview(as_of=local.date(), indicators=values, report_at=clock(),
                   cbc_fx_rows=cbc, system_status="待確認")
    card["altText"] = f"{local.date().isoformat()} 08:55 盤前簡報"
    return card
