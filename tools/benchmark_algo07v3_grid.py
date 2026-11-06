"""Alternate complete diagnostic grids on the live owned selected likelihood.

Extra repetitions are external measurements, not native pipeline timings.
"""

import argparse
import hashlib
import json
import os
import runpy
import sys
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3 import resources, timed

from leo.cli.algo07v3 import supervise, worker, write


def compare_grids(original, candidate, score, endpoints, kwargs, record):
    """Keep all scores, masks, locations, order and grid policy exactly equal."""
    rows = []
    expected = None
    for pair in range(3):
        for side in (('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')):
            options = dict(kwargs)
            if side == 'baseline':
                options.pop('map_batches', None)
            operation = original if side == 'baseline' else candidate
            value = timed(lambda op=operation, kw=options: op(score, endpoints, **kw), rows, side)
            if not value['complete']:
                raise ValueError('Incomplete diagnostic grid cannot qualify speed')
            signature = fingerprint({k: v for k, v in value.items() if k != 'elapsed_seconds'})
            if expected is None:
                expected = signature
            rows[-1].update(pair=pair, signature=signature, exact=signature == expected,
                            grid_points=value['evaluated_points'])
            record(rows)
            if signature != expected:
                raise ValueError('Complete diagnostic grid changed')
    return value


def measured_worker(root):
    from leo.presentation import localization_v3 as presentation

    reference = runpy.run_path(str(root / 'reference.py'))['sample_position_grid']
    original = presentation.sample_position_grid
    calls = []

    def observed(score, endpoints, **kwargs):
        if calls:
            raise ValueError('Expected one final diagnostic grid')
        calls.append(True)
        def record(rows):
            (root / 'trials.json').write_text(json.dumps(rows, indent=2) + '\n')
        return compare_grids(reference, original, score, endpoints, kwargs, record)

    presentation.sample_position_grid = observed
    try:
        return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        presentation.sample_position_grid = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker:
        return measured_worker(args.worker)
    if not all((args.request, args.reference, args.output)):
        parser.error('--request, --reference and --output required')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Use three CPUs and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    write(root / 'request.json', dict(request, output_root=str(root / 'publication')))
    (root / 'reference.py').write_bytes(args.reference.read_bytes())
    paths = [*Path('src').rglob('*.py'), Path(__file__), args.reference,
             root / 'reference.py', root / 'request.json', Path('tools/profile_algo07v3.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(root / 'plan.json', dict(bindings=bindings, affinity=sorted(os.sched_getaffinity(0)),
                                  repeats=3, blas_threads=1, full_pipeline_timing=False))
    write(root / 'resources-start.json', resources())
    with (root / 'worker.log').open('xb') as log:
        outcome = supervise([sys.executable, '-B', str(Path(__file__).resolve()),
                             '--worker', str(root)], log=log, timeout=1200,
                            environment=dict(os.environ, OPENBLAS_NUM_THREADS='1',
                                             OMP_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1'))
    write(root / 'resources-end.json', resources())
    write(root / 'supervisor.json', outcome)
    assert outcome['returncode'] == 0
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    trials = json.loads((root / 'trials.json').read_bytes())
    assert len(trials) == 6 and all(r['completed'] and r['exact'] for r in trials)
    print(json.dumps(trials), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
