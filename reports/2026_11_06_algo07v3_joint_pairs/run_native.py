"""Launch one bounded isolated native pair with persistent launch and terminal records."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--candidate-first', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    if root.is_relative_to('/mnt/qnap01') or (root / 'plan.json').exists():
        parser.error('Fresh local frozen baseline root required')
    command = ['sudo', '-n', 'env', 'PYTHONPATH=src:tools:.', 'OPENBLAS_NUM_THREADS=1',
               'OMP_NUM_THREADS=1', sys.executable, '-B',
               str(Path(__file__).with_name('run_pair.py').resolve()),
               '--root', str(root), '--request', str(args.request.resolve())]
    if args.candidate_first:
        command.append('--candidate-first')
    start = time.time()
    with Path(str(root) + '-worker.log').open('xb') as log:
        worker = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        Path(str(root) + '-launch.json').write_text(json.dumps(dict(
            pid=os.getpid(), worker_pid=worker.pid, command=command, started_unix=start), indent=2))
        status = worker.wait()
    receipt = dict(returncode=status, elapsed_seconds=time.time()-start, finished_unix=time.time())
    Path(str(root) + '-terminal.json').write_text(json.dumps(receipt, indent=2))
    raise SystemExit(status)


if __name__ == '__main__':
    main()
