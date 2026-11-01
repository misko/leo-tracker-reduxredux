"""Use freed worker slots for the late roster; case locks prevent duplicates."""
import subprocess
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import evaluate as e


def work(case):
    if (e.OUT/case/'result.json').exists():return dict(case=case,status='cached')
    log=e.OUT/'logs'/(case+'-tail.log');began=time.monotonic()
    with log.open('w') as f:
        try:
            p=subprocess.run([sys.executable,str(e.OUT/'evaluate.py'),'case',case],stdout=f,stderr=subprocess.STDOUT,timeout=1800)
            status='complete' if p.returncode==0 else 'failed'
        except subprocess.TimeoutExpired:status='timeout'
    return dict(case=case,status=status,seconds=time.monotonic()-began,log=str(log))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prefix');args=parser.parse_args()
    cases=[r['case'] for r in e.read(e.OUT/'protocol.json')['cohort'] if r['stage']=='evaluation' and
           (r['case'].startswith(args.prefix) if args.prefix else r['case']>='DS26-0241')]
    rows=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(work,c) for c in cases]):
            r=f.result();rows.append(r);e.write(e.OUT/(('ds27' if args.prefix else 'tail')+'-jobs.json'),rows);print(r,flush=True)
