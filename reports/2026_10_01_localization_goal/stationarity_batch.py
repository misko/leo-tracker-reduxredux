"""Bounded fixed-state stationarity audit across the frozen 64 scans."""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze_path = HERE/'regression-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    directory = HERE/'stationarity-v1'
    directory.mkdir(exist_ok=False)
    bindings = {str(p.resolve()): digest(p) for p in
                [Path(__file__), HERE/'diagnose_stationarity.py']}
    (directory/'sources.json').write_text(json.dumps(bindings, indent=2))
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))

    def run(unit):
        verify_sources(bindings)
        path = directory/(unit+'.json')
        launch = execute([sys.executable, str(HERE/'diagnose_stationarity.py'), unit,
                          '--output', str(path)], directory, unit, timeout_s=30., env=env)
        verify_sources(bindings)
        launch['receipt_sha256'] = digest(path) if path.exists() else None
        with path.with_suffix('.launch.json').open('x') as stream:
            json.dump(launch, stream, indent=2)
        return launch

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = []
        for launch in pool.map(run, freeze['ordered_units']):
            rows.append(launch)
            if len(rows) % 8 == 0:
                print(json.dumps(dict(completed=len(rows),
                                      successful=sum(r['returncode'] == 0 for r in rows))),
                      flush=True)
    with (directory/'batch.json').open('x') as stream:
        json.dump(dict(launches=rows, original_freeze_sha256=digest(freeze_path)), stream, indent=2)


if __name__ == '__main__':
    main()
