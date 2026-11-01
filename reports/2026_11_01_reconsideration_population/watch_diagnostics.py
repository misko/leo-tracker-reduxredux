"""Bounded local process queue for completed, accepted study outcomes."""
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import evaluate as e


def work(case):
    log=e.OUT/'logs'/(case+'-diagnostics.log')
    with log.open('w') as f:
        try:
            p=subprocess.run([sys.executable,str(e.OUT/'diagnostics.py'),case],stdout=f,stderr=subprocess.STDOUT,timeout=1800)
            return dict(case=case,status='complete' if p.returncode==0 else 'failed')
        except subprocess.TimeoutExpired:return dict(case=case,status='timeout')


if __name__=='__main__':
    already={'DS26-0034','DS26-0046','DS26-0058','DS26-0060'}
    pending={};rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        while True:
            for path in sorted(e.OUT.glob('DS*/result.json')):
                case=path.parent.name
                if case in already:continue
                result=e.read(path)
                if any(r['selected'] for r in result['methods'].values()):pending[pool.submit(work,case)]=case
                already.add(case)
            for f in list(pending):
                if f.done():rows.append(f.result());del pending[f];e.write(e.OUT/'diagnostic-jobs.json',rows);print(rows[-1],flush=True)
            jobs=[]
            for stage in ('evaluation','validation'):
                p=e.OUT/(stage+'-jobs.json')
                if p.exists():jobs+=e.read(p)
            if len(jobs)==175 and not pending:break
            time.sleep(10)
