from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'acquisition_position'))
from common import JOBS


def child(c, i):
    started = time.monotonic()
    try:
        p = subprocess.run([sys.executable, str(HERE / 'diagnose_temporal.py'), c, str(i)], capture_output=True, text=True, timeout=90, env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
        result = dict(cohort=c, index=i, exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired:
        result = dict(cohort=c, index=i, exit_code=124)
    result['elapsed_s'] = time.monotonic() - started
    with (HERE / f'posterior-{c}-{i:02d}.receipt.json').open('x') as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(child, c, i) for c, i, _ in JOBS]):
            print(json.dumps(future.result()), flush=True)
