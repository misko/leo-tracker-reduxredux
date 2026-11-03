"""Bounded preparation and fitting, with explicit terminal receipts."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys
import time
from common import HERE, JOBS, digest, read, verify_sources


def child(stage, cohort, index, arm=None):
    prefix = HERE / f'{stage}-{cohort}-{index:02d}'
    if arm:
        prefix = HERE / (prefix.name + f'-{arm}')
    if stage == 'prepare' and (HERE / f'input-{cohort}-{index:02d}.json').exists():
        verify_sources(read(HERE / f'input-{cohort}-{index:02d}.json'))
        return dict(cohort=cohort, index=index, status='reused_verified')
    start = time.monotonic()
    args = [sys.executable, str(HERE / ('prepare.py' if stage == 'prepare' else 'fit.py')), cohort, str(index)]
    if arm:
        args.append(arm)
    if stage == 'verify':
        args.append('--verify')
    with prefix.with_suffix('.log').open('x') as f:
        try:
            code = subprocess.run(args, stdout=f, stderr=subprocess.STDOUT, timeout=90, env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')).returncode
        except subprocess.TimeoutExpired:
            code = 124
    receipt = dict(stage=stage, cohort=cohort, index=index, arm=arm, exit_code=code, elapsed_s=time.monotonic() - start, log_sha256=digest(prefix.with_suffix('.log')), runner_sha256=digest(HERE / 'run.py'))
    with prefix.with_suffix('.receipt.json').open('x') as f:
        json.dump(receipt, f, indent=2)
    return receipt


if __name__ == '__main__':
    stage = sys.argv[1]
    assert stage in ('prepare', 'verify', 'fit')
    if stage == 'verify':
        print(json.dumps(child(stage, 'original', 0, 'signed')), flush=True)
    else:
        if stage == 'fit':
            assert read(HERE / 'verify-original-00-signed.json')['verified']
        jobs = [(stage, c, i, a) for c, i, _ in JOBS for a in (('doppler', 'signed') if stage == 'fit' else (None,))]
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(child, *job) for job in jobs]):
                print(json.dumps(future.result()), flush=True)
