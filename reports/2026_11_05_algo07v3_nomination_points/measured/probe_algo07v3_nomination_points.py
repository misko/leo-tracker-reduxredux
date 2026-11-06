"""External exact residual-screen prototype: project only used nomination points."""

import argparse
import hashlib
import inspect
import json
import os
import statistics
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import residual_screen
from leo.analysis.localization_v3.region import SearchRegion
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


def nomination_indices(folds):
    indices = {}
    for name, mask, _ in folds:
        ix = np.flatnonzero(mask)
        indices[name] = ix[np.unique(np.linspace(0, len(ix) - 1, min(16, len(ix))).astype(int))]
    query = np.unique(np.concatenate(list(indices.values())))
    columns = {name: np.searchsorted(query, ix) for name, ix in indices.items()}
    return query, columns


def nomination_grids(bank, times, query, positions, *, phase_seconds):
    # Keep full-input validation: an omitted point must not hide a malformed
    # time or extrapolation. Delegate invalid cases to the original path.
    t = np.asarray(times, float)
    knots = np.asarray(bank['time_s'], float)
    shifted = t + phase_seconds
    if (t.ndim != 1 or not np.isfinite(t).all()
            or np.any(shifted < knots[0]) or np.any(shifted > knots[-1])):
        return residual_screen.phase_frequency_grids(bank, times, positions,
                                                     phase_seconds=phase_seconds)
    return residual_screen.phase_frequency_grids(bank, t[query], positions,
                                                 phase_seconds=phase_seconds)


def candidate():
    source = inspect.getsource(residual_screen.screen_candidates)
    changed = source
    replacements = [
        ('        positions = [search_region.latlon',
         '        query, columns = _nomination_indices(folds)\n'
         '        positions = [search_region.latlon'),
        ('grids = phase_frequency_grids(bank, t, positions, phase_seconds=phi)',
         'grids = _nomination_grids(bank, t, query, positions, phase_seconds=phi)'),
        ('y[ix], f[:, ix], t[ix]', 'y[ix], f[:, columns[name]], t[ix]'),
        ('e[:, ix].min(axis=1)', 'e[:, columns[name]].min(axis=1)'),
    ]
    for before, after in replacements:
        if changed.count(before) != 1:
            raise ValueError('Review nomination source boundary: ' + before)
        changed = changed.replace(before, after)
    scope = dict(vars(residual_screen), _nomination_indices=nomination_indices,
                 _nomination_grids=nomination_grids)
    exec(compile(changed, '<nomination-points>', 'exec'), scope)
    return scope['screen_candidates'], source, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    packet = evidence['audit']['additional_recovery']['preflight']
    catalogue, expected = evidence['catalogue'], evidence['audit']['residual_screen']['screen']
    before = fingerprint((packet, catalogue))
    operation, original, changed = candidate()
    (root / 'original.py').write_text(original)
    (root / 'candidate.py').write_text(changed)
    (root / 'plan.json').write_text(json.dumps(dict(
        bindings=bindings, cpus=[*os.sched_getaffinity(0)], repeats=3,
        blas_threads=1, runtime_modified=False), indent=2) + '\n')
    targets = []
    for target in packet['targets']:
        t = np.asarray(target['times_s'])
        folds = [('full', np.ones(len(t), bool), np.zeros(len(t), bool))]
        for seed in residual_screen.SEEDS:
            train, held, _ = residual_screen.split(t, seed)
            if train.sum() >= 8 and held.sum() >= 4:
                folds.append((str(seed), train, held))
        query, _ = nomination_indices(folds)
        targets.append(dict(points=len(t), nomination_points=len(query), folds=len(folds)))
    rows = []
    for pair in range(3):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            callbacks = []
            function = residual_screen.screen_candidates if side == 'baseline' else operation
            began, cpu = time.perf_counter(), time.process_time()
            result = function(packet, catalogue, SearchRegion(tuple(request['search_center'])),
                              on_target=callbacks.append)
            elapsed, used = time.perf_counter() - began, time.process_time() - cpu
            exact = (fingerprint(result) == fingerprint(expected)
                     and fingerprint(callbacks) == fingerprint(expected['targets']))
            row = dict(pair=pair, side=side, seconds=elapsed, cpu_seconds=used, exact=exact)
            rows.append(row)
            (root / f'{pair}-{side}.json').write_text(json.dumps(row, indent=2) + '\n')
            print(json.dumps(row), flush=True)
            assert exact, 'Screen or callback changed; retain failed receipt'
            assert before == fingerprint((packet, catalogue))
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {side: {k: statistics.mean(r[k] for r in rows if r['side'] == side)
                    for k in ('seconds', 'cpu_seconds')} for side in ('baseline', 'candidate')}
    result = dict(rows=rows, means=means, targets=targets, exact=True, bindings=bindings,
                  scientific_receipt=saved['sha256'], full_pipeline_speedup=None,
                  runtime_modified=False)
    (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(means=means, targets=targets)), flush=True)


if __name__ == '__main__':
    main()
