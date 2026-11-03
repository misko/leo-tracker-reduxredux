"""Six warm controlled experiments, two workers and external30s caps."""
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
    parent = HERE/'split-expansion-fit-v1/sources.json'
    assert digest(parent) == parent.with_suffix('.sha256').read_text().strip()
    sources = json.loads(parent.read_text())['source_sha256']
    extra = [HERE/'offset_marginal_density.py', HERE/'offset_grid_quadrature.py', HERE/'offset-marginal-gradient-v1.json',HERE/'offset-marginal-calibration-v2.json', Path(__file__), HERE/'diagnose_offset_marginal_joint.py',
             HERE/'candidate_spatial_expansion_adapter.py',
             HERE/'candidate_offset_marginal_joint.py',
             ROOT/'src/leo/analysis/localization_candidate_set.py',
             ROOT/'src/leo/analysis/localization_candidate_derivatives.py',
             ROOT/'src/leo/analysis/localization_joint_search.py']
    extra.extend((ROOT/'.venv/lib/python3.12/site-packages/numpy/ma').glob('*.py'))
    sources.update({str(p): digest(p) for p in extra})
    pairs = [(u, a) for u in ['DS9-F025', 'DS10-F028', 'DS11-F018']
             for a in ['control', 'candidate']]
    directory = HERE/'offset-marginal-joint-v1'
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
            script = HERE/'diagnose_offset_marginal_joint.py'
            launch = execute([sys.executable, str(script), unit,
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
