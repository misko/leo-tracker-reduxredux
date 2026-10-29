"""Four isolated numerical workers; bounded jobs and explicit terminal accounting."""

import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import debug_fast_graph_unassociated as report


def main(args):
    protocol=report.read(args.study/'protocol.json')
    source=Path(__file__).resolve().parent/'benchmark_graph_covariance.py'
    report.write(args.study/'launch.json',dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        workers=4,per_job_cap_s=300,cases=protocol['selected']))
    def one(case):
        began=time.monotonic();out=args.study/case
        command=[sys.executable,'-B',str(source),'case','--root',protocol['root'],'--case',case,'--output',str(out)]
        with (args.study/(case+'.log')).open('x') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                code=process.wait(timeout=300);status='complete' if code==0 else 'failed'
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                code=process.returncode;status='timeout'
        return dict(case=case,status=status,returncode=code,seconds=time.monotonic()-began)
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(one,case) for case in protocol['selected']]):
            row=future.result();results.append(row);print(row,flush=True)
    report.write(args.study/'execution.json',dict(results=sorted(results,key=lambda r:r['case'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True)
    main(p.parse_args())
