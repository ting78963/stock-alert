"""SOX section for the 08:55 LINE Flex brief; pure formatting, no sends or scheduling."""
from datetime import date


def sox_flex_rows(snapshot, report_day):
    """Return a single safe LINE Flex text row, including stale/missing status."""
    try:
        day = date.fromisoformat(str(report_day)[:10])
        if not snapshot.get("available"):
            raise ValueError("unavailable")
        close_day = date.fromisoformat(snapshot["close_date"])
        age = (day - close_day).days
        if age < 0 or age > 4:
            raise ValueError("stale")
        close = float(snapshot["close"])
        pct = float(snapshot["change_pct"])
        if close <= 0 or not (-100 < pct < 100):
            raise ValueError("invalid")
        sign = "+" if pct > 0 else ""
        value = f"費半 SOX  {close:,.2f}  ({sign}{pct:.2f}%)｜美股 {close_day.isoformat()}"
    except (AttributeError, KeyError, ValueError, TypeError, OverflowError):
        value = "費半 SOX  資料暫不可用"
    return {"type":"text","text":value,"size":"sm","color":"#E5E7EB","wrap":True}
