"""Bounded isolated workers with qualified fallback retained on timeout."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import debug_fast_graph_unassociated as report


def run(args):
    protocol=report.read(args.study/'protocol.json');cases=protocol[args.cohort+'_cases']
    def one(case):
        started=time.monotonic();out=args.study/case
        command=[sys.executable,'-B',str(Path(__file__).parent/'combined_family_reentry.py'),'case',
                 '--root',protocol['root'],'--case',case,'--output',str(out)]
        with (args.study/(case+'.log')).open('x') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=process.wait(timeout=protocol['job_cap_s']);status='complete' if code==0 else 'failed'
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                code=process.returncode;status='timeout'
        return dict(case=case,status=status,returncode=code,seconds=time.monotonic()-started,
                    qualified_fallback_saved=(out/'fallback.json').exists())
    rows=[]
    with ThreadPoolExecutor(max_workers=protocol['workers']) as pool:
        for future in as_completed([pool.submit(one,c) for c in cases]):
            row=future.result();rows.append(row);print(row,flush=True)
    report.write(args.study/(args.cohort+'_execution.json'),rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--cohort',choices=['primary','remaining'],required=True);run(p.parse_args())
