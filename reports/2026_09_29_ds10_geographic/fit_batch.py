"""Launch declared panels only after complete input/provenance verification."""
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def run(job):
    panel,height=job;label=f'{panel}_h{height}'
    folder=HERE/'fit-receipts';folder.mkdir(exist_ok=True)
    command=['uv','run','--no-project','--with','numpy','--with','scipy','python',str(HERE/'fit_panel.py'),panel,str(height)]
    command=['timeout','--kill-after=10','180']+command
    started=time.monotonic()
    with (folder/f'{label}.log').open('x') as log:
        child=subprocess.run(command,cwd=ROOT,env=dict(os.environ,OPENBLAS_NUM_THREADS='1'),stdout=log,stderr=subprocess.STDOUT)
    result=dict(panel=panel,height_m=height,exit_code=child.returncode,elapsed_seconds=time.monotonic()-started,command=command)
    with (folder/f'{label}.json').open('x') as out:json.dump(result,out,indent=2)
    print(label,'exit',child.returncode,'seconds',round(result['elapsed_seconds'],1),flush=True)
    return result


if __name__=='__main__':
    height=int(sys.argv[1]);assert height in (0,20,40)
    subprocess.run([sys.executable,str(HERE/'audit_inputs.py')],check=True)
    assert json.loads((HERE/'input-audit.json').read_text())['complete']
    for name,h in json.loads((HERE/'fit-implementation.json').read_text()).items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==h
    jobs=[(panel,height) for panel in ['N8_0','N8_1','N8_2','N24']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(run,jobs))
    with (HERE/f'fit-batch-h{height}.json').open('x') as out:json.dump(results,out,indent=2)
