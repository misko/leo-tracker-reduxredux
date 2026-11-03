"""Eight fresh held-out scans, two workers, external 90-second enforcement."""
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
    parser.add_argument('--batch', type=int, choices=[1, 2], required=True)
    args = parser.parse_args()
    freeze_path = HERE/'heldout-baseline-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    admission_path = HERE/'ds12-input-admission.json'
    assert digest(admission_path) == freeze['input_admission_sha256']
    admissions = {r['unit']: r for r in json.loads(admission_path.read_text())['rows']}
    directory = HERE/'heldout-baseline-v1'/f'batch-{args.batch:02d}'
    directory.mkdir(parents=True, exist_ok=False)
    units = freeze['ordered_units'][(args.batch-1)*8:args.batch*8]
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))

    def run(unit):
        verify_sources(freeze['source_sha256'])
        verify_sources(admissions[unit]['inputs'])
        output = directory/(unit+'.json')
        command = [sys.executable, str(HERE/'run_heldout.py'), unit,
                   '--arm', 'hard', '--output', str(output)]
        launch = execute(command, directory, unit, env=env)
        verify_sources(freeze['source_sha256'])
        launch.update(freeze_sha256=digest(freeze_path),
                      receipt_sha256=digest(output) if output.exists() else None)
        with (directory/(unit+'.launch.json')).open('x') as stream:
            json.dump(launch, stream, indent=2)
        status = json.loads(output.read_text()).get('status') if output.exists() else 'missing'
        print(json.dumps(dict(unit=unit, status=status, seconds=launch['elapsed_seconds'])),
              flush=True)
        return launch

    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(run, units))
    with (directory/'batch.json').open('x') as stream:
        json.dump(dict(launches=rows, freeze_sha256=digest(freeze_path)), stream, indent=2)


if __name__ == '__main__':
    main()
