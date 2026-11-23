import unittest
from research.sox_web_fetch_v1 import fetch_sox_close

class FakeResponse:
    def __init__(self, text): self.text = text
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit): return self.text.encode()[:limit]

class SoxWebFetchTests(unittest.TestCase):
    def test_valid_dated_page(self):
        def opener(request, timeout): return FakeResponse("<p>DATA AS OF 11/20/2026 8,408.59 -1,011.13 -10.73%</p>")
        result = fetch_sox_close(opener)
        self.assertTrue(result["available"])
        self.assertEqual(result["date"], "2026-11-20")

    def test_page_without_quote_fails_closed(self):
        def opener(request, timeout): return FakeResponse("Data is currently not available")
        result = fetch_sox_close(opener)
        self.assertFalse(result["available"])

    def test_network_error_fails_closed(self):
        def opener(request, timeout): raise OSError("blocked")
        self.assertFalse(fetch_sox_close(opener)["available"])

if __name__ == "__main__":
    unittest.main()
