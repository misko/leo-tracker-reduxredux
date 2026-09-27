"""Run at most twelve missing frozen DS6 fits, with at most two workers."""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE=Path(__file__).resolve().parent


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=5);args=parser.parse_args()
    assert 1<=args.limit<=12
    protocol=json.loads((HERE/'protocol.json').read_text())
    pending=[s for s in protocol['sessions'] if not (HERE/f'{s}.json').exists()][:args.limit]
    def run(session):
        with (HERE/f'{session}.log').open('x') as stream:
            result=subprocess.run([sys.executable,str(HERE/'run_fresh.py'),'--session',session],stdout=stream,stderr=subprocess.STDOUT)
        print(json.dumps(dict(session=session,exit_code=result.returncode)),flush=True)
        return result.returncode
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,pending))
    if any(results):raise SystemExit(1)
