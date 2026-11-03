"""Freeze and score first no-proposal scan per dataset with two bounded workers."""
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
    sources = {}
    units = []
    for folder in ['calibrated-joint-v1', 'calibrated-joint-expansion-v1']:
        parent = HERE/folder/'sources.json'
        assert digest(parent) == parent.with_suffix('.sha256').read_text().strip()
        frozen = json.loads(parent.read_text())
        sources.update(frozen['source_sha256'])
        for unit, arm in frozen['pairs']:
            if arm != 'candidate':
                continue
            path = parent.parent/(unit+'-candidate.json')
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            units.append(unit)
            sources[str(path)] = digest(path)
    assert len(units) == len(set(units)) == 12
    sources.update({str(p): digest(p) for p in [Path(__file__),
        HERE/'audit_calibrated_proposals.py', HERE/'candidate_calibrated_cached_spatial.py',
        HERE/'candidate_calibrated_cached_joint.py',
        ROOT/'src/leo/analysis/localization_epoch_profile.py']})
    directory = HERE/'calibrated-proposal-audit-v1'
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src'), OPENBLAS_NUM_THREADS='1',
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    with (HERE/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_sources(sources)
        directory.mkdir(exist_ok=False)
        freeze = directory/'sources.json'
        freeze.write_text(json.dumps(dict(source_sha256=sources, units=units), indent=2))
        freeze.with_suffix('.sha256').write_text(digest(freeze)+'\n')

        def run(unit):
            path = directory/(unit+'.json')
            launch = execute([sys.executable, str(HERE/'audit_calibrated_proposals.py'),
                              unit, '--output', str(path)], directory, unit,
                             timeout_s=30., env=env)
            verify_sources(sources)
            launch.update(freeze_sha256=digest(freeze),
                          receipt_sha256=digest(path) if path.exists() else None)
            path.with_suffix('.launch.json').write_text(json.dumps(launch, indent=2))
            print(json.dumps(dict(unit=unit, returncode=launch['returncode'],
                                  seconds=launch['elapsed_seconds'])), flush=True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run, units))


if __name__ == '__main__':
    main()
