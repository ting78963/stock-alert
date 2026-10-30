import unittest
from research.per_symbol_exception_policy_v1 import verified_recovery

class VerifiedRecoveryTests(unittest.TestCase):
    def test_missing_older_session_does_not_release(self):
        rows=[("2026-10-30",10,11,9,10,100)]
        self.assertFalse(verified_recovery(rows,"2026-10-29","2026-10-30",["2026-10-29","2026-10-30"]))
    def test_complete_sessions_release(self):
        rows=[("2026-10-29",10,11,9,10,100),("2026-10-30",10,11,9,10,100)]
        self.assertTrue(verified_recovery(rows,"2026-10-29","2026-10-30",["2026-10-29","2026-10-30"]))
    def test_invalid_bar_not_counted(self):
        rows=[("2026-10-30",10,8,9,10,100)]
        self.assertFalse(verified_recovery(rows,"2026-10-30","2026-10-30",["2026-10-30"]))
    def test_missing_calendar_fails_closed(self):
        self.assertFalse(verified_recovery([("2026-10-30",10,11,9,10,100)],"2026-10-30","2026-10-30",[]))

if __name__=="__main__":
    unittest.main()
