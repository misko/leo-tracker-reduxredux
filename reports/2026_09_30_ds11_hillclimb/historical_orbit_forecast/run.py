from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def child(ordinal):
    prefix=HERE/f'states-{ordinal:02d}';started=time.monotonic()
    with prefix.with_suffix('.log').open('x') as f:
        try:code=subprocess.run([sys.executable,str(HERE/'states.py'),str(ordinal)],stdout=f,stderr=subprocess.STDOUT,timeout=90,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')).returncode
        except subprocess.TimeoutExpired:code=124
    result=dict(ordinal=ordinal,exit_code=code,elapsed_s=time.monotonic()-started,log_sha256=digest(prefix.with_suffix('.log')),sources={str(p):digest(p) for p in (Path(__file__),HERE/'states.py',HERE/'PROTOCOL.md')})
    with prefix.with_suffix('.receipt.json').open('x') as f:json.dump(result,f,indent=2)
    return result


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(child,i) for i in range(12)]):print(json.dumps(future.result()),flush=True)
