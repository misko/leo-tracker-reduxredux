"""Apply the unchanged warm Laplace proposal to the previously selected12 scans."""
import fcntl
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    selection = HERE/'student-scale-expansion-v1-freeze.json'
    assert digest(selection) == selection.with_suffix('.sha256').read_text().strip()
    units = json.loads(selection.read_text())['ordered_units']
    pilot = HERE/'nonlinear-laplace-warm-v1/sources.json'
    sources = json.loads(pilot.read_text())['source_sha256']
    sources.update({str(p): digest(p) for p in [Path(__file__), selection, pilot]})
    directory = HERE/'nonlinear-laplace-expansion-v1'
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_sources(sources)
        directory.mkdir(exist_ok=False)
        freeze = directory/'sources.json'
        freeze.write_text(json.dumps(dict(ordered_units=units, source_sha256=sources,
                                         pilot_freeze_sha256=digest(pilot),
                                         policy='Same prior-selected12 scans; unchanged model.'),
                                     indent=2))

        def run(unit):
            path = directory/(unit+'.json')
            verify_sources(sources)
            launch = execute([sys.executable, str(HERE/'diagnose_nonlinear_laplace.py'), unit,
                              '--output', str(path)], directory, unit, timeout_s=60., env=env)
            verify_sources(sources)
            launch.update(expansion_freeze_sha256=digest(freeze),
                          receipt_sha256=digest(path) if path.exists() else None)
            with path.with_suffix('.launch.json').open('x') as stream:
                json.dump(launch, stream, indent=2)
            print(json.dumps(dict(unit=unit, returncode=launch['returncode'],
                                  seconds=launch['elapsed_seconds'])), flush=True)
            return launch

        with ThreadPoolExecutor(max_workers=2) as pool:
            launches = list(pool.map(run, units))
        (directory/'batch.json').write_text(json.dumps(dict(launches=launches), indent=2))


if __name__ == '__main__':
    main()
