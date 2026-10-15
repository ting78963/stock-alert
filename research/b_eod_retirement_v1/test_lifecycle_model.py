# -*- coding: utf-8 -*-
"""Offline-only lifecycle model for B EOD retirement. No production imports, API, LINE, or writes."""
from __future__ import annotations
import threading
import queue
import unittest

class Gate:
    def __init__(self):
        self.lock = threading.RLock()
        self.closed = False
        self.launching = set()
        self.runners = {}

    def claim(self, key):
        with self.lock:
            if self.closed:
                return False
            if key in self.launching or key in self.runners:
                return False
            self.launching.add(key)
            return True

    def publish(self, key, runner):
        with self.lock:
            self.launching.discard(key)
            if self.closed:
                return False
            self.runners[key] = runner
            return True

    def close(self):
        with self.lock:
            self.closed = True
            return len(self.launching)

class Worker:
    """Offline queue worker with positive exit acknowledgement."""
    def __init__(self):
        self.q = queue.Queue()
        self.sealed = False
        self.lock = threading.Lock()
        self.items = []
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def enqueue(self, item):
        with self.lock:
            if self.sealed:
                return False
            self.q.put_nowait(item)
            return True

    def _run(self):
        while True:
            item = self.q.get()
            try:
                if item is None:
                    return
                self.items.append(item)
            finally:
                self.q.task_done()

    def retire(self, timeout=2):
        with self.lock:
            if not self.sealed:
                self.sealed = True
                self.q.put_nowait(None)
        self.thread.join(timeout)
        return not self.thread.is_alive()

class Tests(unittest.TestCase):
    def test_close_blocks_claim(self):
        g = Gate()
        self.assertTrue(g.claim("2026-10-15|2330"))
        self.assertEqual(g.close(), 1)
        self.assertFalse(g.claim("2026-10-15|2317"))
        self.assertFalse(g.publish("2026-10-15|2330", object()))
        self.assertEqual(g.runners, {})

    def test_queue_drained_before_exit(self):
        w = Worker()
        for i in range(1000):
            self.assertTrue(w.enqueue(i))
        self.assertTrue(w.retire())
        self.assertEqual(w.items, list(range(1000)))
        self.assertFalse(w.enqueue(1001))

    def test_concurrent_close_and_publish(self):
        for _ in range(100):
            g = Gate()
            self.assertTrue(g.claim("k"))
            t = threading.Thread(target=g.close)
            t.start()
            accepted = g.publish("k", object())
            t.join()
            self.assertFalse(g.claim("other"))
            if not accepted:
                self.assertNotIn("k", g.runners)

    def test_49_workers(self):
        workers = [Worker() for _ in range(49)]
        for i, w in enumerate(workers):
            self.assertTrue(w.enqueue(i))
        self.assertTrue(all(w.retire() for w in workers))
        self.assertTrue(all(not w.thread.is_alive() for w in workers))

if __name__ == "__main__":
    print("OFFLINE ONLY | NO PRODUCTION IMPORTS | NO API | NO LINE | NO DATA WRITES")
    unittest.main(verbosity=2)
