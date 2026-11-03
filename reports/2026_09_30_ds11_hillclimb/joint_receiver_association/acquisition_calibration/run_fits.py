"""Bound each family calibration, retaining every terminal receipt."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def run(number):
    assert not (HERE / f'fit-{number}.json').exists()
    started = time.monotonic()
    child = subprocess.run(['timeout', '--kill-after=5s', '90s', sys.executable, str(HERE / 'fit_family.py'), str(number)], capture_output=True, text=True, env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
    result = dict(family=number, returncode=child.returncode, stdout=child.stdout, stderr=child.stderr, elapsed_s=time.monotonic() - started)
    with (HERE / f'fit-receipt-{number}.json').open('x') as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(run, range(8)):
            print(json.dumps(result), flush=True)
