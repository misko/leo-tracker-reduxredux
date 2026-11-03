"""Bounded per-scan T1-AT replication; preserve completed N01/N02 artifacts."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import signal

from run import run

BASE = Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
OUT = Path('/srv/bulk/leo/t1-at-v1-replication-20261004/remaining')


def worker(label):
    target = OUT/label
    if (target/'summary.json').exists():
        return json.loads((target/'summary.json').read_text())
    def timeout(*_):
        raise TimeoutError(f'{label}: 15-minute per-scan budget reached')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(900)
    try:
        run(BASE/label/'seed-timing-v6', label, target)
    finally:
        signal.alarm(0)
    return json.loads((target/'summary.json').read_text())


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scans',nargs='+',default=[f'N{i:02}' for i in range(3,17)])
    p.add_argument('--workers',type=int,default=4)
    args=p.parse_args()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(worker,s) for s in args.scans]):
            print('COMPLETED_SCAN',json.dumps(future.result()),flush=True)
