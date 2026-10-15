# -*- coding: utf-8 -*-
"""Offline dynamic checks for B EOD close barrier, queue drain and thread exit.
Extract only selected function ASTs: never import or start the production worker.
"""
import ast,threading,queue,unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[2].joinpath("production_worker_v2_shared_ws.py").read_text(encoding="utf-8")
TREE=ast.parse(SOURCE)
NAMES={"b_eod_begin_close","b_eod_queue_drained","b_eod_thread_exited"}
funcs=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
assert {f.name for f in funcs}==NAMES
ns={"_lock":threading.RLock(),"_runners":{},"_queues":{},"_worker_threads":{},"_b_eod_closing":set()}
exec(compile(ast.Module(body=funcs,type_ignores=[]),"<B EOD selected functions>","exec"),ns)
class TestClose(unittest.TestCase):
    def setUp(self):
        ns["_runners"].clear();ns["_queues"].clear();ns["_worker_threads"].clear();ns["_b_eod_closing"].clear()
    def test_close_requires_active_runner(self):
        self.assertFalse(ns["b_eod_begin_close"]("x"))
    def test_close_sets_barrier(self):
        ns["_runners"]["x"]=object();ns["_queues"]["x"]=queue.Queue()
        self.assertTrue(ns["b_eod_begin_close"]("x"))
        self.assertIn("x",ns["_b_eod_closing"])
    def test_queue_drained_only_after_task_done(self):
        q=queue.Queue();q.put(1);ns["_queues"]["x"]=q
        self.assertFalse(ns["b_eod_queue_drained"]("x"))
        self.assertEqual(q.get(),1)
        self.assertFalse(ns["b_eod_queue_drained"]("x"))
        q.task_done()
        self.assertTrue(ns["b_eod_queue_drained"]("x"))
    def test_thread_exit_is_real(self):
        go=threading.Event()
        t=threading.Thread(target=lambda:go.wait(2))
        ns["_worker_threads"]["x"]=t;t.start()
        try:self.assertFalse(ns["b_eod_thread_exited"]("x"))
        finally:go.set();t.join(2)
        self.assertTrue(ns["b_eod_thread_exited"]("x"))
    def test_missing_thread_is_not_exited(self):
        self.assertFalse(ns["b_eod_thread_exited"]("x"))
if __name__=="__main__":unittest.main(verbosity=2)
