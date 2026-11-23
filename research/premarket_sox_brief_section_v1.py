"""Pure SOX brief assembly for the planned 08:55 report; no scheduler or LINE push."""
from research.premarket_sox_yahoo_chart_v1 import fetch_sox_chart
from research.premarket_sox_flex_section_v1 import sox_flex_rows


def build_sox_brief_section(report_day, fetcher=fetch_sox_chart):
    """One bounded fetch, one Flex row. Never prevent the rest of the brief."""
    try:
        snapshot = fetcher()
    except Exception:
        snapshot = {"available": False}
    return sox_flex_rows(snapshot, report_day)
