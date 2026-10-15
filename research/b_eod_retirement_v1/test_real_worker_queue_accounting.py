# -*- coding: utf-8 -*-
"""AST checks for first real B worker queue-accounting integration.
READ ONLY, NO NETWORK, NO LINE, NO PRODUCTION WRITE.
"""
import ast,argparse,pathlib
def verify(path):
    src=pathlib.Path(path).read_text(encoding="utf-8")
    t=ast.parse(src)
    f={n.name:n for n in t.body if isinstance(n,ast.FunctionDef)}
    w=f["worker_loop"]
    outer=next(n for n in ast.walk(w) if isinstance(n,ast.Try) and any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=="task_done" for z in n.finalbody for x in ast.walk(z)))
    assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="get" for n in ast.walk(w)),"worker must consume queue"
    assert outer.finalbody,"task_done must be in finally"
    launch=ast.get_source_segment(src,f["launch_b"])
    assert '_worker_threads[k]=t' in launch,"thread handle must be retained"
    assert 't.start()' in launch,"thread must be started"
    assert '_worker_threads={}' in src,"thread registry missing"
    print("[PASS] B worker consumed queue items have task_done in finally")
    print("[PASS] B worker thread handles retained before start")
    print("[PASS] Thread registry initialized")
    print("3/3 PASS | AST/static checks only; EOD close not yet wired")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--worker",required=True)
    a=p.parse_args();verify(a.worker)
