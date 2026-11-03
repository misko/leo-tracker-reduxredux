"""Three predeclared cold pilots, at most two workers, external90s each."""
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
    freeze = HERE/'regression-v1-freeze.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    sources = json.loads(freeze.read_text())['source_sha256']
    for name in ['run_track_fragments.py', 'track_fragments.py', 'track_fragments_batch.py']:
        sources[str(HERE/name)] = digest(HERE/name)
    sources[str(HERE/'signal-provenance-v1.json')] = digest(HERE/'signal-provenance-v1.json')
    verify_sources(sources)
    units = ['DS9-F001', 'DS10-F056', 'DS11-F001']
    directory = HERE/'track-fragments-v1'
    directory.mkdir(exist_ok=False)
    frozen = directory/'sources.json'
    frozen.write_text(json.dumps(dict(source_sha256=sources, units=units,
        selection='Keep baseline tracks; append unused-visit fragments with6points/3seconds, '
                  'split gaps>4seconds; no GPS. Original cold acquisition/3hard starts.'),
                                 indent=2))
    frozen.with_suffix('.sha256').write_text(digest(frozen)+'\n')
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src'), OPENBLAS_NUM_THREADS='1',
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')

    def run(unit):
        output = directory/(unit+'.json')
        launch = execute([sys.executable, str(HERE/'run_track_fragments.py'), unit,
                          '--arm', 'hard', '--output', str(output)], directory, unit, env=env)
        verify_sources(sources)
        launch['freeze_sha256'] = digest(frozen)
        launch['receipt_sha256'] = digest(output) if output.exists() else None
        (directory/(unit+'.launch.json')).write_text(json.dumps(launch, indent=2))
        print(json.dumps(launch), flush=True)

    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run, units))


if __name__ == '__main__':
    main()
