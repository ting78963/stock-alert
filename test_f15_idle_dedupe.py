import unittest
from unittest.mock import patch
from datetime import datetime
import f15_trajectory_store as t

class StopLoop(Exception):
    pass

class IdleTests(unittest.TestCase):
    def run_case(self, complete, status):
        with patch.object(t.OUT.__class__, 'mkdir'), patch.object(t, 'datetime') as dt, patch.object(t, 'days', return_value=['2026-11-26']), patch.object(t, 'report_and_trajectory_complete', side_effect=complete) as check, patch.object(t, 'build_day', return_value={'status':status}) as build, patch.object(t.time,'sleep',side_effect=[None,StopLoop]):
            dt.now.return_value=datetime(2026,11,26,20)
            with self.assertRaises(StopLoop):
                t.loop()
            return build.call_count,check.call_count
    def test_existing_complete(self):
        self.assertEqual(self.run_case([True],'ok'),(0,1))
    def test_zero_complete(self):
        self.assertEqual(self.run_case([False,True],'no_events'),(1,2))
    def test_pending_retries(self):
        self.assertEqual(self.run_case([False,False,False,False],'no_events'),(2,4))

if __name__=='__main__':
    unittest.main()
