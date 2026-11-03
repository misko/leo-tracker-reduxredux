"""Frozen nine-scan pilot, at most two fits, bounded warm diagnostics."""
import fcntl
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parent = HERE/'fixed-reference-nuisance-v1/sources.json'
    assert digest(parent) == parent.with_suffix('.sha256').read_text().strip()
    sources = json.loads(parent.read_text())['source_sha256']
    files = [Path(__file__), HERE/'balanced_group_pilot.py', HERE/'balanced_group_objective.py',
             HERE/'test_balanced_group.py',
             ROOT/'src/leo/analysis/localization_prior.py']
    sources.update({str(p): digest(p) for p in files})
    pairs = [(u, a) for u in ['DS9-F045', 'DS10-F075', 'DS11-F035', 'DS9-F065', 'DS10-F112', 'DS11-F052', 'DS9-F085', 'DS10-F149', 'DS11-F069']
             for a in ['control', 'balanced']]
    directory = HERE/'balanced-group-expansion-v1'
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src'), OPENBLAS_NUM_THREADS='1',
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_sources(sources)
        directory.mkdir(exist_ok=False)
        freeze = directory/'sources.json'
        freeze.write_text(json.dumps(dict(source_sha256=sources, pairs=pairs), indent=2))
        freeze.with_suffix('.sha256').write_text(digest(freeze)+'\n')

        def run(pair):
            unit, arm = pair
            name = unit+'-'+arm
            path = directory/(name+'.json')
            launch = execute([sys.executable, str(HERE/'balanced_group_pilot.py'), unit,
                              '--arm', arm, '--output', str(path)], directory, name,
                             timeout_s=30., env=env)
            verify_sources(sources)
            launch.update(freeze_sha256=digest(freeze),
                          receipt_sha256=digest(path) if path.exists() else None)
            path.with_suffix('.launch.json').write_text(json.dumps(launch, indent=2))
            print(json.dumps(dict(name=name, returncode=launch['returncode'],
                                  seconds=launch['elapsed_seconds'])), flush=True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run, pairs))


if __name__ == '__main__':
    main()
