# B memory probe: isolated process, no Runner instances or API calls
import gc, runpy, sys, threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FILES=['fugle_b_live_runner_v2_p1_final.py','fugle_b_engine_v2_p1.py','f13_incremental_state.py']
def rss():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'): return int(line.split()[1])/1024
def snap(label):
    gc.collect()
    print(f'{label:35s} RSS={rss():.2f} MiB threads={threading.active_count()}',flush=True)
def main():
    print('ISOLATED READ-ONLY PROBE | no Runner / Fugle / LINE / production writes')
    missing=[f for f in FILES if not (ROOT/f).exists()]
    if missing: sys.exit('STOP missing: '+', '.join(missing))
    snap('baseline')
    held=[]
    for f in FILES:
        for i in range(5):
            held.append(runpy.run_path(str(ROOT/f),run_name='__b_memory_probe__'))
            snap(f'{f} copy {i+1}')
    gate=threading.Event()
    threads=[threading.Thread(target=gate.wait,daemon=True) for _ in range(50)]
    for t in threads:t.start()
    snap('50 idle threads added')
    gate.set()
    for t in threads:t.join()
    snap('threads joined')
    print('CAUTION: not a full 100-stock B simulation.')
if __name__=='__main__':main()
