"""Six prespecified pilots with two workers and external 90-second deadlines."""
import fcntl
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze_path = HERE/'discrepancy-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    directory = HERE/'discrepancy-v1'
    directory.mkdir(exist_ok=False)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))

    def run(pair):
        unit, arm = pair
        name = unit+'-'+arm
        output = directory/(name+'.json')
        verify_sources(freeze['source_sha256'])
        command = [sys.executable, str(HERE/'run_discrepancy.py'), unit,
                   '--arm', arm, '--output', str(output)]
        launch = execute(command, directory, name, env=env)
        verify_sources(freeze['source_sha256'])
        launch.update(freeze_sha256=digest(freeze_path),
                      receipt_sha256=digest(output) if output.exists() else None)
        with (directory/(name+'.launch.json')).open('x') as stream:
            json.dump(launch, stream, indent=2)
        status = json.loads(output.read_text()).get('status') if output.exists() else 'missing'
        print(json.dumps(dict(unit=unit, arm=arm, status=status,
                              seconds=launch['elapsed_seconds'])), flush=True)
        return launch

    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=2) as pool:
            launches = list(pool.map(run, freeze['ordered_pairs']))
    with (directory/'batch.json').open('x') as stream:
        json.dump(dict(launches=launches, freeze_sha256=digest(freeze_path)), stream, indent=2)


if __name__ == '__main__':
    main()
