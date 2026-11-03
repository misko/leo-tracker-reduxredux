"""Bounded preparation, verification or position-start workers."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import time
from common import HERE,JOBS,read,digest


def main(stage):
    jobs=[]
    for cohort,index,family in JOBS:
        if stage=='prepare':jobs.append((f'prepare-{cohort}-{index:02d}','prepare.py',[cohort,str(index)]))
        elif stage=='preflight':
            assert read(HERE/f'prepare-{cohort}-{index:02d}.receipt.json')['exit_code']==0
            jobs.append((f'preflight-{cohort}-{index:02d}','fit.py',['preflight',cohort,str(index)]))
        elif stage=='fit':
            assert read(HERE/f'preflight-{cohort}-{index:02d}.json')['passed']
            for arm in ('doppler','signed'):
                for seed in (0,1):jobs.append((f'fit-{cohort}-{index:02d}-{arm}-{seed}','fit.py',[cohort,str(index),arm,str(seed)]))
        else:raise ValueError(stage)
    def launch(job):
        name,script,args=job;stem=HERE/name;start=time.monotonic()
        with stem.with_suffix('.log').open('x') as log:
            result=subprocess.run(['timeout','--kill-after=5s','90s',sys.executable,str(HERE/script),*args],stdout=log,stderr=subprocess.STDOUT)
        receipt=dict(job=name,exit_code=result.returncode,elapsed_s=time.monotonic()-start,
                     sources={str(p):digest(p) for p in (HERE/'run.py',HERE/script,HERE/'PROTOCOL.md',stem.with_suffix('.log'))})
        with stem.with_suffix('.receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
        print(json.dumps({k:v for k,v in receipt.items() if k!='sources'}),flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(launch,jobs))


if __name__=='__main__':main(sys.argv[1])
