# -*- coding: utf-8 -*-
"""Offline tests for B EOD queue barrier. No production imports, network or LINE."""
import queue,threading,time,unittest
from worker_drain import DrainController,consuming_worker

class TestDrain(unittest.TestCase):
    def test_drains_all_and_exits(self):
        d=DrainController();q=queue.Queue(maxsize=2000);seen=[]
        t=threading.Thread(target=consuming_worker,args=(q,seen));t.start()
        for i in range(1000):self.assertTrue(d.admit("x",q,i))
        result=d.close_and_join("x",q,t,timeout=5)
        self.assertTrue(result.drained);self.assertTrue(result.exited)
        self.assertEqual(seen,list(range(1000)))
        self.assertFalse(d.admit("x",q,1001))
    def test_concurrent_producer_cannot_add_after_close(self):
        d=DrainController();q=queue.Queue(maxsize=2000);seen=[]
        t=threading.Thread(target=consuming_worker,args=(q,seen));t.start()
        stop=threading.Event();accepted=[]
        def produce():
            i=0
            while not stop.is_set():
                if d.admit("x",q,i):accepted.append(i)
                i+=1
                time.sleep(0.0001)
        p=threading.Thread(target=produce);p.start()
        time.sleep(0.03)
        result=d.close_and_join("x",q,t,timeout=5)
        stop.set();p.join(2)
        self.assertTrue(result.exited)
        self.assertEqual(seen,accepted)
        self.assertFalse(d.admit("x",q,"late"))
    def test_timeout_fail_closed(self):
        d=DrainController();q=queue.Queue(maxsize=10)
        self.assertTrue(d.admit("x",q,1))
        t=threading.Thread(target=lambda:None);t.start();t.join()
        result=d.close_and_join("x",q,t,timeout=0.02)
        self.assertFalse(result.drained)
        self.assertEqual(result.reason,"queue_timeout")
        self.assertFalse(d.admit("x",q,2))
    def test_no_producer_after_close(self):
        d=DrainController();q=queue.Queue();seen=[]
        t=threading.Thread(target=consuming_worker,args=(q,seen));t.start()
        self.assertTrue(d.close_and_join("x",q,t,timeout=2).exited)
        self.assertFalse(d.admit("x",q,1))

if __name__=="__main__":unittest.main(verbosity=2)
