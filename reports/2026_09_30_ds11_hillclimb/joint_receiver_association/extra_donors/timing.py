"""Bounded timing-only calibration for the four numerical donors."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time
from context import load,fast,digest
from timing_model import solve

HERE=Path(__file__).resolve().parent


def worker(index):
    started=time.monotonic();doc,config,xy,capture,entry,sources=load(index)
    fast.baseline.profile=fast.profile
    result=solve(fast.Stationary(doc,config),xy)
    sources.update({str(p):digest(p) for p in (Path(__file__),HERE/'timing_model.py',HERE/'TRANSFER_PROTOCOL.md')})
    result.update(ordinal=index,family=capture['family'],session_id=entry['session_id'],sources=sources,
                  horizontal_refitted=False,elapsed_s=time.monotonic()-started)
    with (HERE/f'timing-{index:02d}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k not in ('sources','starts')},indent=2))


def launch(i):
    start=time.monotonic();stem=HERE/f'timing-{i:02d}'
    with stem.with_suffix('.log').open('x') as log:
        r=subprocess.run(['timeout','--kill-after=5s','90s',sys.executable,str(Path(__file__)),'worker',str(i)],stdout=log,stderr=subprocess.STDOUT)
    receipt=dict(index=i,exit_code=r.returncode,elapsed_s=time.monotonic()-start,sources={str(p):digest(p) for p in (Path(__file__),HERE/'timing_model.py',stem.with_suffix('.log'))})
    with stem.with_suffix('.receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k!='sources'}),flush=True)


if __name__=='__main__':
    if len(sys.argv)>1:worker(int(sys.argv[2]))
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(launch,range(4)))
