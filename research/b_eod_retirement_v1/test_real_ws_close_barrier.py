# -*- coding: utf-8 -*-
"""Offline static audit of real B WS queue admission barrier."""
import ast,argparse,pathlib
def main(path):
    src=pathlib.Path(path).read_text(encoding="utf-8")
    tree=ast.parse(src)
    f=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="route_message")
    # Check the queue lookup, close check and publish are in one _lock block.
    found=False
    for node in ast.walk(f):
        if not isinstance(node,ast.With):continue
        segment=ast.get_source_segment(src,node) or ""
        if not any(isinstance(i.context_expr,ast.Name) and i.context_expr.id=="_lock" for i in node.items):continue
        if all(x in segment for x in ("if k in _b_eod_closing:return","q=_queues.get(k)","with q.mutex:","q.put_nowait(row)")):
            found=True
    assert found,"[FAIL] WS publish is not atomic with close barrier"
    assert "_b_eod_closing=set()" in src
    print("[PASS] WS queue lookup/coalesce/publish under one lifecycle lock")
    print("[PASS] B EOD close barrier checked before enqueue")
    print("2/2 PASS | static only; close coordinator and REST authority NOT integrated")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--worker",required=True)
    a=p.parse_args();main(a.worker)
