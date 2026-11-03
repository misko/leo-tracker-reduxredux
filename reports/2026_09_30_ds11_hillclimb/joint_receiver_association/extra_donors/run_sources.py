from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time
from context import digest
HERE=Path(__file__).resolve().parent


def launch(i):
    start=time.monotonic();stem=HERE/f'donor-{i:02d}'
    with stem.with_suffix('.log').open('x') as log:
        r=subprocess.run(['timeout','--kill-after=5s','90s',sys.executable,str(HERE/'source_export.py'),str(i)],stdout=log,stderr=subprocess.STDOUT)
    result=dict(index=i,exit_code=r.returncode,elapsed_s=time.monotonic()-start,sources={str(p):digest(p) for p in (Path(__file__),HERE/'source_export.py',stem.with_suffix('.log'))})
    with stem.with_suffix('.receipt.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='sources'}),flush=True)


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(launch,range(4)))
