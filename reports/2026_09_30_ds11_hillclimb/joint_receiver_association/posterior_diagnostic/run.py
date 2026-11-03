from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'acquisition_position'))
from common import JOBS, read, digest, verify_sources


def child(cohort, index):
    prefix = HERE / f'diagnostic-{cohort}-{index:02d}'
    if prefix.with_suffix('.json').exists():
        verify_sources(read(prefix.with_suffix('.json')))
        return dict(cohort=cohort, index=index, status='reused_verified')
    started = time.monotonic()
    with prefix.with_suffix('.log').open('x') as f:
        try:
            code = subprocess.run([sys.executable, str(HERE / 'diagnose.py'), cohort, str(index)], stdout=f, stderr=subprocess.STDOUT, timeout=90, env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')).returncode
        except subprocess.TimeoutExpired:
            code = 124
    result = dict(cohort=cohort, index=index, exit_code=code, elapsed_s=time.monotonic() - started, log_sha256=digest(prefix.with_suffix('.log')), runner_sha256=digest(Path(__file__)))
    with prefix.with_suffix('.receipt.json').open('x') as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == '__main__':
    if '--pilot' in sys.argv:
        print(json.dumps(child('original', 0)), flush=True)
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(child, c, i) for c, i, _ in JOBS]):
                print(json.dumps(future.result()), flush=True)
