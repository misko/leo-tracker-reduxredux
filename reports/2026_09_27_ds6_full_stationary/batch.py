"""Bounded batches of missing all-track fits; at most three workers."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

HERE=Path(__file__).resolve().parent

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=12);args=parser.parse_args();assert 1<=args.limit<=12
    p=json.loads((HERE/'protocol.json').read_text())
    selected=[s for s in p['sessions'] if not (HERE/f'{s}.json').exists()][:args.limit]
    def run(session):
        with (HERE/f'{session}.log').open('x') as log:
            r=subprocess.run([sys.executable,str(HERE/'run_full.py'),'--session',session],stdout=log,stderr=subprocess.STDOUT)
        print(json.dumps(dict(session=session,exit_code=r.returncode)),flush=True);return r.returncode
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,selected))
    if any(results):raise SystemExit(1)
