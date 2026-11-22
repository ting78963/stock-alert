import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from taiex_fugle_store_v1 import date_ranges, fetch_range, update, read_store


class FakeResponse:
    status_code=200
    def raise_for_status(self): pass
    def json(self):
        return {"symbol":"IX0001","timeframe":"D","data":[{"date":"2026-11-20","close":27000.0}]}


class FakeSession:
    def get(self, url, params, headers, timeout):
        assert url.endswith("/IX0001")
        assert params["timeframe"]=="D"
        assert headers["X-API-KEY"]=="fake"
        return FakeResponse()


class FugleTAIEXTest(unittest.TestCase):
    def test_fetch_ix0001(self):
        self.assertEqual(fetch_range(date(2026,11,1),date(2026,11,22),session=FakeSession(),api_key="fake"),[{"date":"2026-11-20","close":27000.0}])

    def test_chunk_under_one_year(self):
        ranges=list(date_ranges(date(2023,11,1),date(2026,11,22)))
        self.assertTrue(all((b-a).days < 365 for a,b in ranges))
        self.assertEqual(ranges[0][0],date(2023,11,1))
        self.assertEqual(ranges[-1][1],date(2026,11,22))

    def test_bootstrap_checkpoint_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"taiex.json"
            calls=[]
            def fake(a,b,session=None,api_key=None):
                calls.append((a,b))
                if len(calls)==3: raise ConnectionError("simulated failure")
                return [{"date":a.isoformat(),"close":100.0}]
            with patch("taiex_fugle_store_v1.fetch_range",side_effect=fake):
                with self.assertRaises(ConnectionError):
                    update("2026-11-22",path=path)
            self.assertEqual(len(read_store(path)),2)
            self.assertEqual(read_store(path)[-1]["date"],calls[1][0].isoformat())


if __name__=="__main__":
    unittest.main()
