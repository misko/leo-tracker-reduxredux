"""Bounded checkpoint launch with durable terminal receipt, independent of terminal UI."""

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
    parser.add_argument('--stage', choices=('predictive', 'numerical'), required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.exists() or root.is_relative_to('/mnt/qnap01'):
        parser.error('Fresh local root required')
    reference = Path('/srv/bulk/leo-dev/algo07v3-joint-audit-native-0102-20261106')
    command = ['timeout', '--kill-after=5s', '1200s', 'taskset', '-c', '0,1,2',
               sys.executable, '-B', 'tools/benchmark_algo07v3_final_joint.py',
               '--request', str(reference / 'candidate-request.json'),
               '--native-comparison', str(reference / 'comparison.json'),
               '--stage', args.stage, '--output', str(root)]
    env = dict(os.environ, PYTHONPATH='src:tools:.', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    start = time.time()
    with Path(str(root) + '-worker.log').open('xb') as log:
        worker = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        Path(str(root) + '-launch.json').write_text(json.dumps(dict(
            pid=os.getpid(), worker_pid=worker.pid, command=command, started_unix=start), indent=2))
        status = worker.wait()
    receipt = dict(returncode=status, elapsed_seconds=time.time() - start,
                   finished_unix=time.time())
    Path(str(root) + '-terminal.json').write_text(json.dumps(receipt, indent=2))
    raise SystemExit(status)


if __name__ == '__main__':
    main()
