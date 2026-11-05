"""External fixed-phase geometry experiment; never imported by runtime inference."""

import argparse
import hashlib
import inspect
import json
import os
import statistics
import textwrap
import time
from pathlib import Path

import algo07v3_preposition_geometry_oracle as original
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.continuous_curve_fit import (
    paired_phase_states,
    phase_frequency_from_states,
)
from leo.analysis.research.prepared_phase_geometry import prepare_phase_geometry
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


def geometry(problem, xy):
    """Prepare fixed phase states; orbit arrays are fixed inputs, replaced on change."""
    buffers = tuple(bank[key] for bank in (problem.sky, problem.mode_bank)
                    for key in ('time_s', 'position_km', 'velocity_km_s'))
    grid = tuple((a.dtype.str, a.shape, a.tobytes()) for a in
                 map(np.asarray, (problem.flat_times, problem.flat_labels, problem.reference)))
    cached = getattr(problem, '_probe_phase_geometry', None)
    if (cached is None or grid != cached[1] or
            not all(a is b for a, b in zip(buffers, cached[0], strict=True))):
        center = prepare_phase_geometry(problem.sky, problem.mode_bank,
                                        problem.flat_times, problem.flat_labels, problem.reference)
        states = [paired_phase_states(problem.sky, problem.flat_times,
                                      problem.flat_labels, problem.reference + offset)
                  for offset in (0.01, -0.01)]
        for pair in states:
            for value in pair:
                value.setflags(write=False)
        cached = buffers, grid, center, states
        problem._probe_phase_geometry = cached
    coordinates = problem.scan.search_region.latlon(xy)
    frequency, elevation, modes = cached[2].evaluate(*coordinates)
    plus, minus = [phase_frequency_from_states(*state, *coordinates)[0] for state in cached[3]]
    return frequency, elevation, (plus - minus) / (2 * 0.01), modes


def candidate_function():
    oracle = Path(original.__file__)
    if hashlib.sha256(oracle.read_bytes()).hexdigest() != (
            '38535668aa81bb2116250225c457721b91a77fbd81084e8675a109ad3aa21c3f'):
        raise ValueError('Frozen original geometry calculator changed')
    source = textwrap.dedent(inspect.getsource(original.JointMarginal.calculate))
    begin = source.index('    frequency, elevation = paired_phase_frequency(')
    end = source.index('    intercept = absolute_phase_linearization(', begin)
    mode_begin = source.index('    modes = paired_frequency_modes(')
    mode_end = source.index('    orbital = np.zeros(', mode_begin)
    code = (source[:begin] + '    frequency, elevation, derivative, modes = geometry(self, xy)\n'
            + source[end:mode_begin] + source[mode_end:])
    namespace = dict(vars(original), geometry=geometry)
    exec(compile(code, '<fixed-phase-position-geometry>', 'exec'), namespace)
    return namespace['calculate'], source, code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Fresh output required')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('Pin OPENBLAS_NUM_THREADS=1 before starting Python')
    files = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py'), Path(original.__file__)]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the numerical runtime')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    prepared, initial = evidence['preparation'], evidence['audit']['initial']
    noise_bytes = (json.dumps(prepared['noise'], default=_json_value,
                             sort_keys=True, allow_nan=False) + '\n').encode()
    scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                    hashlib.sha256(noise_bytes).hexdigest(), genuine=True)
    winner = next(row for row in initial['choices']
                  if row['hypothesis'] == initial['selected_hypothesis'])
    candidate, source, code = candidate_function()
    functions = dict(baseline=original.JointMarginal.calculate, candidate=candidate)
    positions = np.random.default_rng(20261105).uniform(-12.5, 12.5, (50, 2))
    results = []
    for arm in ('c0', 'fitted_c'):
        for pair in range(3):
            order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
            expected = None
            for side in order:
                p = NormalPosition(scan, winner['node'], scan.radio_sigma_hz, arm == 'fitted_c')
                began, cpu = time.perf_counter(), time.process_time()
                values = [functions[side](p, x, geometry_only=True) for x in positions]
                seconds, cpu_seconds = time.perf_counter() - began, time.process_time() - cpu
                signature = fingerprint(values)
                if expected is not None and signature != expected:
                    raise ValueError('Geometry or features differ')
                expected = signature
                results.append(dict(arm=arm, pair=pair, side=side, seconds=seconds,
                                    cpu_seconds=cpu_seconds, points=len(p.values), exact=True))
    means = {side: statistics.mean(r['seconds'] for r in results if r['side'] == side)
             for side in functions}
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    result = dict(rows=results, mean_seconds=means, exact=True, positions=positions.tolist(),
                  bindings=bindings, affinity=sorted(os.sched_getaffinity(0)),
                  blas_threads=1, runtime=request['runtime'],
                  prepared_input_benchmark=True, runtime_modified=False, full_pipeline_speedup=None,
                  reference_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  candidate_source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  scientific_receipt=saved['sha256'])
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(means))


if __name__ == '__main__':
    main()
