"""Three matched pilot pairs, two workers, hard30s warm-diagnostic cap."""
import fcntl
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    pairs = [(u, a) for u in ['DS9-F001', 'DS10-F056', 'DS11-F001']
             for a in ['control', 'mixture']]
    files = [Path(__file__), HERE/'diagnose_sample_mixture.py', HERE/'sample_mixture_adapter.py',
             HERE.parents[1]/'src/leo/analysis/localization_sample_mixture.py']
    sources = {str(p): digest(p) for p in files}
    directory = HERE/'sample-mixture-v1'
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory.mkdir(exist_ok=False)
        freeze = directory/'sources.json'
        freeze.write_text(json.dumps(dict(ordered_pairs=pairs, source_sha256=sources), indent=2))

        def run(pair):
            unit, arm = pair
            name = unit+'-'+arm
            path = directory/(name+'.json')
            verify_sources(sources)
            launch = execute([sys.executable, str(HERE/'diagnose_sample_mixture.py'), unit,
                              '--arm', arm, '--output', str(path)],
                             directory, name, timeout_s=30., env=env)
            verify_sources(sources)
            launch.update(source_freeze_sha256=digest(freeze),
                          receipt_sha256=digest(path) if path.exists() else None)
            with path.with_suffix('.launch.json').open('x') as stream:
                json.dump(launch, stream, indent=2)
            print(json.dumps(dict(unit=unit, arm=arm, returncode=launch['returncode'],
                                  seconds=launch['elapsed_seconds'])), flush=True)
            return launch

        with ThreadPoolExecutor(max_workers=2) as pool:
            launches = list(pool.map(run, pairs))
        (directory/'batch.json').write_text(json.dumps(dict(launches=launches), indent=2))


if __name__ == '__main__':
    main()
