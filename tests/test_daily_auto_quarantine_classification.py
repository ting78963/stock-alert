"""Regression checks for daily maintenance quarantine classification."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("daily_builder", ROOT / "research" / "phase1_fugle_daily_builder_v1.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class QuarantineClassificationTests(unittest.TestCase):
    def test_provider_failures_are_not_stock_halts(self):
        for error in (
            "HTTPError: 401 unauthorized",
            "HTTPError: 403 forbidden",
            "HTTPError: 429 rate limited",
            "HTTPError: 500 internal",
            "HTTPError: 503 unavailable",
            "URLError:  timeout",
            "TimeoutError:  timeout",
        ):
            with self.subTest(error=error):
                self.assertTrue(module.is_provider_failure(error))

    def test_individual_failures_are_not_provider_outages(self):
        for error in (
            "HTTPError: 404 HTTP Error 404: Not Found",
            "ValueError:  quarantined stock has no verified latest daily candle",
            "ValueError:  missing data array",
        ):
            with self.subTest(error=error):
                self.assertFalse(module.is_provider_failure(error))


if __name__ == "__main__":
    unittest.main()
