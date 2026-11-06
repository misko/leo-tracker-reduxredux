"""Alternate complete screens while omitting discarded azimuth calculations."""

import argparse
import hashlib
import inspect
import json
import os
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

import algo07v3_preazimuth_screen_oracle as oracle
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import residual_screen
from leo.analysis.localization_v3.region import SearchRegion
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


def elevation_and_rate(position_ecef_km, velocity_ecef_km_s, observer_ecef_km, enu_matrix):
    """Retain the original look-angle math for the two outputs screening uses."""
    relative = position_ecef_km - observer_ecef_km
    east_north_up = relative @ enu_matrix.T
    slant_range = np.linalg.norm(relative, axis=-1)
    east = east_north_up[..., 0]
    north = east_north_up[..., 1]
    up = east_north_up[..., 2]
    elevation = np.rad2deg(np.arctan2(up, np.hypot(east, north)))
    with np.errstate(invalid="ignore", divide="ignore"):
        range_rate = np.where(
            slant_range > 0.0,
            np.einsum("...i,...i->...", relative, velocity_ecef_km_s) / slant_range,
            0.0,
        )
    return elevation, range_rate


def operations():
    original = inspect.getsource(oracle.phase_frequency_grids)
    before = '        _, elevation, _, rate = look_angles(position, velocity, observer, rotation)'
    after = '        elevation, rate = _elevation_and_rate(position, velocity, observer, rotation)'
    if original.count(before) != 1:
        raise ValueError('Review azimuth source boundary')
    helper = inspect.getsource(elevation_and_rate).replace('def elevation_and_rate(',
                                                        'def _elevation_and_rate(', 1)
    changed = helper + '\n\n' + original.replace(before, after)
    functions = {}
    for label, source in (('baseline', original), ('candidate', changed)):
        scope = dict(vars(oracle))
        exec(compile(source, f'<azimuth-{label}>', 'exec'), scope)
        functions[label] = scope['phase_frequency_grids']
    return functions, dict(baseline=original, candidate=changed)


@contextmanager
def projection(operation):
    original = residual_screen.phase_frequency_grids
    try:
        residual_screen.phase_frequency_grids = operation
        yield
    finally:
        residual_screen.phase_frequency_grids = original


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
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__), Path(oracle.__file__),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    packet = evidence['audit']['additional_recovery']['preflight']
    catalogue, expected = evidence['catalogue'], evidence['audit']['residual_screen']['screen']
    before = fingerprint((packet, catalogue))
    functions, sources = operations()
    for label, source in sources.items():
        (root / f'{label}.py').write_text(source)
    (root / 'plan.json').write_text(json.dumps(dict(bindings=bindings, repeats=3,
        cpus=list(os.sched_getaffinity(0)), blas_threads=1, runtime_modified=False), indent=2)+'\n')
    rows = []
    for pair in range(3):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            callbacks = []
            with projection(functions[side]):
                began, cpu = time.perf_counter(), time.process_time()
                result = residual_screen.screen_candidates(
                    packet, catalogue, SearchRegion(tuple(request['search_center'])),
                    on_target=callbacks.append)
                elapsed, used = time.perf_counter() - began, time.process_time() - cpu
            exact = (fingerprint(result) == fingerprint(expected)
                     and fingerprint(callbacks) == fingerprint(expected['targets']))
            unchanged = before == fingerprint((packet, catalogue))
            row = dict(pair=pair, side=side, seconds=elapsed, cpu_seconds=used,
                       exact=exact, unchanged_inputs=unchanged)
            rows.append(row)
            (root / f'{pair}-{side}.json').write_text(json.dumps(row, indent=2)+'\n')
            print(json.dumps(row), flush=True)
            assert exact and unchanged, 'Complete screen mismatch; retain failed receipt'
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
               for p, digest in bindings.items())
    means = {side: {k: statistics.mean(r[k] for r in rows if r['side'] == side)
                    for k in ('seconds', 'cpu_seconds')} for side in ('baseline', 'candidate')}
    result = dict(rows=rows, means=means, exact=True, bindings=bindings,
                  scientific_receipt=saved['sha256'], full_pipeline_speedup=None,
                  runtime_modified=False)
    (root / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(means=means)), flush=True)


if __name__ == '__main__':
    main()
