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
    parent = HERE/'candidate-joint-expansion-v1/sources.json'
    assert digest(parent) == parent.with_suffix('.sha256').read_text().strip()
    sources = json.loads(parent.read_text())['source_sha256']
    extra = [Path(__file__), HERE/'diagnose_broad_proposals.py',
             HERE/'candidate_cached_joint.py', HERE/'candidate_cached_spatial.py',
             HERE/'diagnose_candidate_reassociation.py',
             ROOT/'src/leo/analysis/localization_epoch_profile.py',
             HERE/'candidate_reassociation_spatial.py',
             HERE/'candidate_reassociation_joint.py',
             HERE/'candidate_spatial_expansion_adapter.py',
             HERE/'candidate_joint_expansion_adapter.py',
             ROOT/'src/leo/analysis/localization_candidate_set.py',
             ROOT/'src/leo/analysis/localization_candidate_derivatives.py',
             ROOT/'src/leo/analysis/localization_joint_search.py']
    extra.extend((ROOT/'.venv/lib/python3.12/site-packages/numpy/ma').glob('*.py'))
    sources.update({str(p): digest(p) for p in extra})
    audit = HERE/'candidate-reassociation-audit-v1.json'
    assert digest(audit) == audit.with_suffix('.sha256').read_text().strip()
    sources[str(audit)] = digest(audit)
    units = [r['unit'] for r in json.loads(audit.read_text())['rows']]
    pairs = [(u, a) for u in units for a in ['control', 'candidate']]
    equivalence = HERE/'candidate-cached-audit-v1.json'
    assert digest(equivalence) == equivalence.with_suffix('.sha256').read_text().strip()
    sources[str(equivalence)] = digest(equivalence)
    directory = HERE/'broad-proposals-v1'
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
            script = HERE/'diagnose_broad_proposals.py'
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
