# -*- coding: utf-8 -*-
"""Offline bootstrap and 14:30 incomplete-close regressions."""
import json
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
import taiex_fugle_store_v1 as store

class Bootstrap1430Tests(unittest.TestCase):
    def test_bootstrap_checkpoints_two_chunks_and_resumes(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"index.json"
            today=date(2026,11,23)
            calls=[]
            def fake_fetch(start,end,**kwargs):
                calls.append((start,end))
                return [{"date":start.isoformat(),"close":20000.0}]
            with patch.object(store,"fetch_range",side_effect=fake_fetch):
                first=store.update(as_of=today,path=path,max_chunks=2)
                self.assertEqual(len(calls),2)
                self.assertEqual(first["stored"],2)
                state=json.loads(path.read_text())
                self.assertEqual(state["covered_through"],calls[-1][1].isoformat())
                second=store.update(as_of=today,path=path,max_chunks=2)
                self.assertEqual(len(calls),4)
                self.assertGreater(second["stored"],first["stored"])

    def test_recent_cached_candle_does_not_skip_older_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"index.json"
            today=date(2026,11,23)
            start=date(2023,11,1)
            store.write_store(path,[{"date":today.isoformat(),"close":20000}],covered_through=start.isoformat())
            calls=[]
            def fake_fetch(a,b,**kwargs):
                calls.append((a,b))
                return [{"date":a.isoformat(),"close":19000}]
            with patch.object(store,"fetch_range",side_effect=fake_fetch):
                result=store.update(as_of=today,path=path,max_chunks=1)
            self.assertEqual(calls[0][0],start+timedelta(days=1))
            self.assertEqual(result["latest"],today.isoformat())
            self.assertEqual(result["stored"],2)

    def test_completed_history_fetches_only_new_day(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"index.json"
            today=date(2026,11,23)
            yesterday=today-timedelta(days=1)
            store.write_store(path,[{"date":yesterday.isoformat(),"close":20000}],covered_through=yesterday.isoformat())
            calls=[]
            def fake_fetch(a,b,**kwargs):
                calls.append((a,b))
                return [{"date":today.isoformat(),"close":20010}]
            with patch.object(store,"fetch_range",side_effect=fake_fetch):
                result=store.update(as_of=today,path=path)
                again=store.update(as_of=today,path=path)
            self.assertEqual(calls,[(today,today)])
            self.assertEqual(result["latest"],today.isoformat())
            self.assertEqual(again["fetched_rows"],0)

    def test_missing_today_candle_does_not_mark_today_covered(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"index.json"
            today=date(2026,11,23)
            yesterday=today-timedelta(days=1)
            store.write_store(path,[{"date":yesterday.isoformat(),"close":20000}],covered_through=yesterday.isoformat())
            with patch.object(store,"fetch_range",return_value=[]) as fetch:
                store.update(as_of=today,path=path)
                self.assertEqual(json.loads(path.read_text())["covered_through"],yesterday.isoformat())
                store.update(as_of=today,path=path)
                self.assertEqual(fetch.call_count,2)

if __name__=="__main__":
    unittest.main()
