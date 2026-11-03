"""Run the frozen four-capture eligibility audit with bounded children."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def one(i):
    started=time.monotonic();stem=HERE/f'capture-{i:02d}'
    with stem.with_suffix('.log').open('x') as log:
        result=subprocess.run(['timeout','--kill-after=5s','90s',sys.executable,str(HERE/'inspect_capture.py'),str(i)],stdout=log,stderr=subprocess.STDOUT)
    receipt=dict(ordinal=i,exit_code=result.returncode,elapsed_s=time.monotonic()-started,
                 sources={str(p):digest(p) for p in (Path(__file__),HERE/'inspect_capture.py',HERE/'policy.py',HERE/'PROTOCOL.md',stem.with_suffix('.log'))})
    with stem.with_suffix('.receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k!='sources'}),flush=True)


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(one,range(4)))
