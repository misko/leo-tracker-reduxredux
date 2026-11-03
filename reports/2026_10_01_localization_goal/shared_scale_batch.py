"""Bounded six-scan batches for the unchanged shared-satellite model."""
import argparse
import fcntl
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', required=True, type=int, choices=[1, 2])
    args = parser.parse_args()
    freeze_path = HERE/'shared-scale-expansion-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    root = HERE/'shared-scale-expansion-v1'
    root.mkdir(exist_ok=True)
    directory = root/f'batch-{args.batch:02}'
    directory.mkdir(exist_ok=False)
    units = freeze['ordered_units'][(args.batch-1)*6:args.batch*6]
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))

    def run(unit):
        output = directory/(unit+'.json')
        verify_sources(freeze['source_sha256'])
        launch = execute([sys.executable, str(HERE/'run_shared_scale.py'), unit,
                          '--arm', 'satellite', '--output', str(output)], directory, unit, env=env)
        verify_sources(freeze['source_sha256'])
        launch.update(freeze_sha256=digest(freeze_path),
                      receipt_sha256=digest(output) if output.exists() else None)
        with output.with_suffix('.launch.json').open('x') as stream:
            json.dump(launch, stream, indent=2)
        status = json.loads(output.read_text()).get('status') if output.exists() else 'missing'
        print(json.dumps(dict(unit=unit, status=status, seconds=launch['elapsed_seconds'])),
              flush=True)
        return launch

    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=2) as pool:
            launches = list(pool.map(run, units))
    with (directory/'batch.json').open('x') as stream:
        json.dump(dict(launches=launches, freeze_sha256=digest(freeze_path)), stream, indent=2)


if __name__ == '__main__':
    main()
