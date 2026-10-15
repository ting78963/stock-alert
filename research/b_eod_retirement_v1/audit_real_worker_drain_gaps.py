# -*- coding: utf-8 -*-
"""Read-only integration gap audit against the REAL shared B worker source.
This test intentionally identifies blockers; it does not change production.
"""
import ast,argparse,pathlib,sys

def body(fn):
    return ast.get_source_segment(SOURCE,fn) or ""
def check(path):
    global SOURCE
    SOURCE=pathlib.Path(path).read_text(encoding="utf-8")
    tree=ast.parse(SOURCE)
    funcs={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    for name in ("worker_loop","route_message","retire_runner","launch_b","clock_loop"):
        if name not in funcs:raise RuntimeError("Missing worker function: "+name)
    worker=body(funcs["worker_loop"]);route=body(funcs["route_message"])
    retire=body(funcs["retire_runner"]);launch=body(funcs["launch_b"])
    findings={
        "queue_task_done_missing":"task_done(" not in worker,
        "route_gets_queue_before_publish":"with _lock:q=_queues.get(k)" in route and "with q.mutex:" in route,
        "retire_sentinel_can_be_lost":"q.put_nowait(None)" in retire and "except Exception:pass" in retire,
        "worker_thread_handle_not_stored":"threading.Thread(target=worker_loop,args=(k,r,q),daemon=True).start()" in launch,
        "worker_returns_without_queue_accounting":"if item is None:return" in worker,
    }
    for k,v in findings.items():print(("[CONFIRMED] " if v else "[REVIEW] ")+k)
    print("SUMMARY",{"confirmed_blockers":sum(findings.values()),"checks":len(findings)})
    print("This is a blocker audit, NOT a passing integration test.")
    return 0 if all(findings.values()) else 2

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--worker",required=True)
    a=p.parse_args()
    raise SystemExit(check(a.worker))
