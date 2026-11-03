from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'acquisition_position'))
from common import JOBS, read, digest


def child(cohort, index, arm, verify=False):
    prefix = HERE / f"{'verify' if verify else 'fit'}-{cohort}-{index:02d}-{arm}"
    started = time.monotonic()
    command = [sys.executable, str(HERE / 'fit_time.py'), cohort, str(index), arm] + (['--verify'] if verify else [])
    with prefix.with_suffix('.log').open('x') as f:
        try:
            code = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, timeout=90, env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')).returncode
        except subprocess.TimeoutExpired:
            code = 124
    result = dict(cohort=cohort, index=index, arm=arm, exit_code=code, elapsed_s=time.monotonic() - started, log_sha256=digest(prefix.with_suffix('.log')), runner_sha256=digest(Path(__file__)))
    with prefix.with_suffix('.receipt.json').open('x') as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == '__main__':
    if '--verify' in sys.argv:
        print(json.dumps(child('original', 0, 'candidate', True)), flush=True)
    else:
        assert read(HERE / 'verify-original-00-candidate.json')['verified']
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(child, c, i, a) for c, i, _ in JOBS for a in ('doppler', 'candidate')]):
                print(json.dumps(future.result()), flush=True)
