import datetime as dt
import importlib.util
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location("restart_preflight", Path(__file__).resolve().parents[1] / "tools" / "restart_preflight.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
TPE = ZoneInfo("Asia/Taipei")
NOW = dt.datetime(2026, 11, 5, 19, 0, tzinfo=TPE)

def ready():
    return dict(schema="daily_maintenance_state_v2", date="2026-11-05",
                stages=["DAILY_K", "F10"], line_sent=True,
                line_accepted_at="2026-11-05T16:30:00+08:00",
                f15_complete=True, active_trading_jobs=0,
                disk_ok=True, database_ok=True, restart_attempted=False)

class RestartGateTests(unittest.TestCase):
    def test_eligible(self):
        self.assertTrue(mod.check(ready(), NOW)[0])
    def test_rejects_market_hours_even_if_all_flags_true(self):
        morning = NOW.replace(hour=10)
        self.assertFalse(mod.check(ready(), morning)[0])

    def test_rejects_late_night(self):
        late = NOW.replace(hour=23, minute=10)
        self.assertFalse(mod.check(ready(), late)[0])

    def test_wait(self):
        s = ready()
        s["line_accepted_at"] = "2026-11-05T17:30:00+08:00"
        self.assertFalse(mod.check(s, NOW)[0])
    def test_stale(self):
        s = ready()
        s["date"] = "2026-11-04"
        self.assertFalse(mod.check(s, NOW)[0])
    def test_no_f15(self):
        s = ready()
        s["f15_complete"] = False
        self.assertFalse(mod.check(s, NOW)[0])
    def test_no_disk(self):
        s = ready()
        s["disk_ok"] = False
        self.assertFalse(mod.check(s, NOW)[0])
    def test_unknown_jobs(self):
        s = ready()
        s.pop("active_trading_jobs")
        self.assertFalse(mod.check(s, NOW)[0])
    def test_duplicate(self):
        s = ready()
        s["restart_attempted"] = True
        self.assertFalse(mod.check(s, NOW)[0])
    def test_malformed_stages(self):
        s = ready()
        s["stages"] = None
        self.assertFalse(mod.check(s, NOW)[0])
    def test_boolean_jobs_rejected(self):
        s = ready()
        s["active_trading_jobs"] = False
        self.assertFalse(mod.check(s, NOW)[0])
    def test_future_timestamp_rejected(self):
        s = ready()
        s["line_accepted_at"] = "2026-11-05T20:00:00+08:00"
        self.assertFalse(mod.check(s, NOW)[0])
    def test_old_schema(self):
        s = ready()
        s["schema"] = "daily_maintenance_state_v1"
        self.assertFalse(mod.check(s, NOW)[0])

if __name__ == "__main__":
    unittest.main()
