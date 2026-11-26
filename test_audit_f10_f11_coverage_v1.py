import unittest
from research.audit_f10_f11_coverage_v1 import audit

class CoverageAuditTests(unittest.TestCase):
    def test_missing_and_excluded_are_separate(self):
        records = {
            "1101": {"symbol": "1101", "market": "TSE", "securityType": "01", "industry": "01"},
            "1102": {"symbol": "1102", "market": "TSE", "securityType": "01", "industry": "02"},
            "1103": {"symbol": "1103", "market": "TSE", "securityType": "01"},
        }
        report = audit({"1101", "1102", "1103", "1104"}, records)
        self.assertEqual(report["f10_symbols"], 4)
        self.assertEqual(report["f11_cached"], 3)
        self.assertEqual(report["f11_eligible_by_existing_rules"], 1)
        self.assertEqual(report["universe_missing_f11"], 1)
        self.assertEqual(report["universe_missing_valid_f11"], 2)
        self.assertEqual(report["comparison_universe"], "f10_proxy_only")
        self.assertEqual(report["missing_valid_symbols"], ["1103", "1104"])

    def test_snapshot_is_authoritative_for_comparison(self):
        report = audit({"1101", "1102"}, {"1101": {"symbol": "1101", "market": "TSE", "securityType": "01", "industry": "01"}}, {"1101", "9999"})
        self.assertEqual(report["comparison_universe"], "snapshot")
        self.assertEqual(report["missing_valid_symbols"], ["9999"])

    def test_no_files_does_not_invent_counts(self):
        report = audit(None, None)
        self.assertIsNone(report["f10_symbols"])
        self.assertIsNone(report["f11_cached"])
        self.assertIsNone(report["universe_missing_valid_f11"])

if __name__ == "__main__":
    unittest.main()
