# -*- coding: utf-8 -*-
"""B EOD research-only worker shutdown primitive.

Guarantees:
- stop new queue admission before drain
- wait for already admitted queue work to finish
- use a sentinel, never clear queued candles
- join actual thread before reporting exit
- no runner recognition/LINE/production imports
"""
from __future__ import annotations
import queue,threading,time
from dataclasses import dataclass

@dataclass(frozen=True)
class DrainResult:
    drained:bool
    exited:bool
    reason:str

class DrainController:
    def __init__(self):
        self._lock=threading.RLock()
        self._closing=set()
        self._inflight={}
    def admit(self,key,q,item):
        with self._lock:
            if key in self._closing:return False
            # enqueue atomically with close: no producer can add after close starts
            try:q.put_nowait(item)
            except queue.Full:return False
            return True
    def close_and_join(self,key,q,thread,timeout=30):
        with self._lock:
            self._closing.add(key)
        # Queue.join() has no timeout: poll unfinished_tasks without holding mutex.
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            with q.mutex:
                unfinished=q.unfinished_tasks
            if unfinished==0:break
            time.sleep(0.02)
        else:return DrainResult(False,False,"queue_timeout")
        try:q.put_nowait(None)
        except queue.Full:return DrainResult(True,False,"sentinel_full")
        remaining=max(0,deadline-time.monotonic())
        thread.join(remaining)
        if thread.is_alive():return DrainResult(True,False,"thread_alive")
        return DrainResult(True,True,"ok")

def consuming_worker(q,seen):
    while True:
        x=q.get()
        try:
            if x is None:return
            seen.append(x)
        finally:q.task_done()
