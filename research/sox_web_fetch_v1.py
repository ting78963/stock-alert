"""Isolated, bounded SOX page fetch. Research-only; no scanner or LINE side effects."""
from urllib.request import Request, urlopen
from research.sox_nasdaq_web_v1 import parse_nasdaq_sox_html

SOX_URL = "https://indexes.nasdaq.com/Index/Overview/sox"


def fetch_sox_close(opener=urlopen, timeout=8):
    request = Request(SOX_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; StockAlertMorningBrief/1.0)", "Accept": "text/html"})
    try:
        with opener(request, timeout=timeout) as response:
            html = response.read(1_000_001)
        if len(html) > 1_000_000:
            return {"available": False, "reason": "page_too_large"}
        parsed = parse_nasdaq_sox_html(html.decode("utf-8", errors="replace"))
        return {"available": True, **parsed}
    except (OSError, UnicodeError, ValueError) as exc:
        return {"available": False, "reason": type(exc).__name__, "source": "nasdaq_sox_overview"}
