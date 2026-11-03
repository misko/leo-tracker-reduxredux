"""Five predeclared warm search diagnostics, at most two workers and 30s each."""
import fcntl
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    units = ['DS9-F001', 'DS10-F056', 'DS11-F001', 'DS10-F066', 'DS9-F060']
    parents = {u: str(HERE/('group-influence-'+('worst-' if i >= 3 else '')+u+'.json'))
               for i, u in enumerate(units)}
    files = [Path(__file__), HERE/'diagnose_deletion_bridge.py',
             HERE/'regression-v1-freeze.json', *map(Path, parents.values())]
    sources = {str(p): digest(p) for p in files}
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
    directory = HERE/'deletion-bridge-v1'
    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory.mkdir(exist_ok=False)
        freeze_path = directory/'sources.json'
        freeze_path.write_text(json.dumps(dict(ordered_units=units, parents=parents,
                                               source_sha256=sources), indent=2))

        def run(unit):
            verify_sources(sources)
            path = directory/(unit+'.json')
            launch = execute([sys.executable, str(HERE/'diagnose_deletion_bridge.py'), unit,
                              '--output', str(path)], directory, unit, timeout_s=30., env=env)
            verify_sources(sources)
            launch['receipt_sha256'] = digest(path) if path.exists() else None
            launch['source_freeze_sha256'] = digest(freeze_path)
            with path.with_suffix('.launch.json').open('x') as stream:
                json.dump(launch, stream, indent=2)
            print(json.dumps(launch), flush=True)
            return launch

        with ThreadPoolExecutor(max_workers=2) as pool:
            launches = list(pool.map(run, units))
        (directory/'batch.json').write_text(json.dumps(dict(launches=launches), indent=2))


if __name__ == '__main__':
    main()
