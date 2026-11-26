"""Read-only gate for the existing daily restart coordinator."""
import json
from pathlib import Path

def market_restart_ready(now, day, state_path):
    if now.date().isoformat() != day:
        return False, "date_mismatch"
    # Never interrupt the market maintenance delivery window.
    if (now.hour, now.minute) < (17, 0):
        return False, "before_market_window"
    try:
        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
        if isinstance(state, dict) and state.get("sent_date") == day:
            return True, "market_report_sent"
    except (OSError, ValueError, TypeError):
        pass
    if (now.hour, now.minute) >= (18, 10):
        return True, "market_report_unconfirmed_fallback"
    return False, "waiting_market_report"
