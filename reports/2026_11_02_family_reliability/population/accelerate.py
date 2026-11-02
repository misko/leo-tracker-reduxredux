"""Four extra low-priority workers; disjoint reverse-ID scheduling, no GPS."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from algo06_science.common import read,write

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
LOCK=threading.Lock()

def main():
    os.setpriority(os.PRIO_PROCESS,0,10)
    policy=read(ROOT/'protocol.json');records=sorted(policy['cases'],key=lambda r:r['case'],reverse=True)
    began=time.monotonic();deadline=began+1200
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH='src:tools')
    def loop(index):
        while time.monotonic()<deadline:
            with LOCK:
                candidates=[r for r in records if not (ROOT/(r['case']+'.log')).exists() and not (ROOT/'cases'/r['case']/'result.json').exists()]
                if not candidates:return
                row=candidates[0];path=ROOT/(row['case']+'.log');f=path.open('x')
            try:
                with f:
                    subprocess.run([sys.executable,str(ROOT/'run.py'),'--case',row['case']],cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT,
                        timeout=min(600,deadline-time.monotonic()),check=True)
                result=read(ROOT/'cases'/row['case']/'result.json')
                print('extra',index,row['case'],result['status'],round(time.monotonic()-began),flush=True)
            except Exception as exc:
                write(ROOT/'cases'/row['case']/'extra-attempt-error.json',dict(reason=repr(exc),seconds=time.monotonic()-began))
                print('extra',index,row['case'],repr(exc),flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(loop,range(4)))
    write(ROOT/'extra_completion.json',dict(seconds=time.monotonic()-began,max_seconds=1200,extra_workers=4,schedule='reverse lexical case ID, no GPS'))

if __name__=='__main__':main()
