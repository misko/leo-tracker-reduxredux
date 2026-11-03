from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def child(cohort,index,arm,verify=False):
    prefix=HERE/f"{'verify' if verify else 'fit'}-{cohort}-{index:02d}-{arm}"
    started=time.monotonic()
    command=[sys.executable,str(HERE/'fit_epoch.py'),cohort,str(index),arm]+(['--verify'] if verify else [])
    with prefix.with_suffix('.log').open('x') as f:
        try:
            code=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=90,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')).returncode
        except subprocess.TimeoutExpired:
            code=124
    result=dict(cohort=cohort,index=index,arm=arm,exit_code=code,elapsed_s=time.monotonic()-started,log_sha256=digest(prefix.with_suffix('.log')),runner_sha256=digest(Path(__file__)))
    with prefix.with_suffix('.receipt.json').open('x') as f:
        json.dump(result,f,indent=2)
    return result


if __name__=='__main__':
    if '--verify' in sys.argv:
        print(json.dumps(child('original',0,'timing',True)),flush=True)
    else:
        assert json.loads((HERE/'verify-original-00-timing.json').read_text())['verified']
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(child,c,i,a) for c,i in [('original',0),('additional',1)] for a in ('doppler','timing')]):
                print(json.dumps(future.result()),flush=True)
