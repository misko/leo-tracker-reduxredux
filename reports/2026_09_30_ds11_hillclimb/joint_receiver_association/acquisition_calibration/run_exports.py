"""Bounded donor exports; retain terminal receipts, never overwrite data."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def run(index):
    start = time.monotonic()
    path = HERE / f'donor-{index:02d}.json'
    if path.exists():
        data = json.loads(path.read_text())
        for source, expected in data['sources'].items():
            assert hashlib.sha256(Path(source).read_bytes()).hexdigest() == expected, source
        return dict(index=index, status='reused_verified', elapsed_s=time.monotonic() - start)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    child = subprocess.run(['timeout', '--kill-after=5s', '90s', sys.executable, str(HERE / 'export_donor.py'), str(index)], capture_output=True, text=True, env=env)
    result = dict(index=index, status='completed' if child.returncode == 0 else 'failed', returncode=child.returncode, stdout=child.stdout, stderr=child.stderr, elapsed_s=time.monotonic() - start)
    with (HERE / f'export-receipt-{index:02d}.json').open('x') as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(run, range(23)):
            print(json.dumps(result), flush=True)
