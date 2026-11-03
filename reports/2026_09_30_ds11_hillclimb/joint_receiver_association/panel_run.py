"""Bounded children with durable execution receipts, three workers maximum."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from doppler_pilot import digest

HERE = Path(__file__).resolve().parent


def run(index, arm):
    start = time.monotonic()
    command = [sys.executable, str(HERE / 'position_run.py'), '--index', str(index), '--arm', arm]
    log = HERE / f'position-{index:02d}-{arm}.log'
    with log.open('x') as stream:
        try:
            completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=90, env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'))
            code = completed.returncode
        except subprocess.TimeoutExpired:
            code = 124
    result = dict(index=index, arm=arm, command=command, exit_code=code, wall_s=time.monotonic() - start, log=str(log), log_sha256=digest(log), runner_sha256=digest(Path(__file__)), protocol_sha256=digest(HERE / 'PANEL_PROTOCOL.md'))
    path = HERE / f'position-{index:02d}-{arm}.receipt.json'
    with path.open('x') as f:
        json.dump(result, f, indent=2)
    return result


def main():
    assert (HERE / 'panel-inputs.json').exists()
    jobs = [(i, a) for i in (4, 8, 12, 20, 24, 28) for a in ('doppler', 'receiver', 'signed', 'swapped', 'permuted')]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run, i, a) for i, a in jobs]
        for f in as_completed(futures):
            r = f.result()
            print(json.dumps({k: r[k] for k in ('index', 'arm', 'exit_code', 'wall_s')}), flush=True)


if __name__ == '__main__':
    main()
