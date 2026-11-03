"""Bounded fixed-state uncertainty construction for the16 frozen held-out scans."""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze_path = HERE/'heldout-uncertainty-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    directory = HERE/'heldout-uncertainty-v1'
    directory.mkdir(exist_ok=False)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))

    def run(unit):
        path = directory/(unit+'.json')
        verify_sources(freeze['source_sha256'])
        launch = execute([sys.executable, str(HERE/'run_heldout_uncertainty.py'), unit,
                          '--output', str(path)], directory, unit, timeout_s=30., env=env)
        verify_sources(freeze['source_sha256'])
        launch.update(receipt_sha256=digest(path) if path.exists() else None,
                      freeze_sha256=digest(freeze_path))
        with path.with_suffix('.launch.json').open('x') as stream:
            json.dump(launch, stream, indent=2)
        status = json.loads(path.read_text()).get('status') if path.exists() else 'missing'
        print(json.dumps(dict(unit=unit, status=status, seconds=launch['elapsed_seconds'])),
              flush=True)
        return launch

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(run, freeze['ordered_units']))
    with (directory/'batch.json').open('x') as stream:
        json.dump(dict(launches=rows, freeze_sha256=digest(freeze_path)), stream, indent=2)


if __name__ == '__main__':
    main()
