from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE = Path(__file__).resolve().parent


def child(number):
    started = time.monotonic()
    try:
        process = subprocess.run([sys.executable, str(HERE / 'fit.py'), str(number)], capture_output=True, text=True, timeout=90, env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
        result = dict(family=number, exit_code=process.returncode, stdout=process.stdout, stderr=process.stderr)
    except subprocess.TimeoutExpired:
        result = dict(family=number, exit_code=124)
    result['elapsed_s'] = time.monotonic() - started
    with (HERE / f'receipt-{number}.json').open('x') as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(child, i) for i in range(2, 8)]):
            print(json.dumps(future.result()), flush=True)
