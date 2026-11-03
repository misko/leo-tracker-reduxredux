"""Bounded synthetic stress check of screen bounds and exact sparse native scores."""

import argparse
import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import profile_algo07_glrt as fixture_tools
from native_exact_columns import ExactColumns
from native_screen_bounds import bound as floating_bound
from probe_native_screen import screen_grid
from stage_native_glrt_runtime import digest, verify, verify_files


def full_grid(oracle):
    rows = []
    for frequencies, count in oracle.tiles:
        grid = oracle.native(oracle.values, oracle.template, frequencies,
                             oracle.starts, oracle.stops, oracle.offsets,
                             oracle.prefix, oracle.rate, oracle.epochs)
        rows.extend(grid[:count])
    return np.asarray(rows)


def run(candidate, output):
    build = json.loads((candidate / 'screen-probe.json').read_text())
    integer = build.get('screen_kind') == 'integer_vnni'
    bound = floating_bound
    if integer:
        from native_integer_screen import bound
    base = Path(build['base'])
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    files = [Path(__file__).with_name(name) for name in
             ('check_native_screen_numerics.py', 'native_exact_columns.py',
              'native_screen_bounds.py', 'probe_native_screen.py')]
    if integer:
        files += [Path(__file__).with_name(n) for n in
                  ('native_integer_screen.py', 'interval_coarse_selection.py')]
    pins = {p.name: digest(p) for p in files}
    if integer and build.get('transformer_sha256') != pins['native_integer_screen.py']:
        raise ValueError('Integer bound differs from the built screen implementation')
    fixture_tools.use_source(base)
    from leo.analysis.starlink import acquisition

    extension = next((candidate / 'src/leo/analysis/starlink').glob('_native_acquisition*.so'))
    spec = importlib.util.spec_from_file_location('_screen._native_acquisition', extension)
    screen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(screen)
    if acquisition._folded_anchor_score_grid_backend() != 'avx2_fma':
        raise RuntimeError('Explicit AVX2/FMA hardware and deployed extension required')
    geometry = SimpleNamespace(
        OFDM_SYMBOL_DURATION_S=.0001, FRAME_RATE_HZ=1000,
        _power_prefix=acquisition._power_prefix,
        _native_acquisition=acquisition._native_acquisition,
        _folded_anchor_score_grid_backend=acquisition._folded_anchor_score_grid_backend,
        _constant_grid_step=acquisition._constant_grid_step)
    rng = np.random.default_rng(20261103)
    source = rng.normal(size=512) + 1j*rng.normal(size=512)
    template = rng.normal(size=64) + 1j*rng.normal(size=64)
    patterns = [('noise', source),
                ('alternating', np.tile([1+1j, -1-1j], 256)),
                ('prefix-cancellation', np.r_[source[:256], source[256:]*2.**-40])]
    scales = (-100, -30, 0, 30, 36)
    if integer:
        patterns = [('noise', np.rint(source.real*32) + 1j*np.rint(source.imag*32)),
                    ('alternating', np.tile([1+1j, -1-1j], 256)),
                    ('zero-tail', np.r_[np.ones(256)*(1+1j), np.zeros(256)]),
                    ('constant', np.ones(512)*(1+1j))]
        scales = (1, 127, 1023, 32767)
    results = []
    began = time.time_ns()
    for pattern, values in patterns:
        for x_exponent in scales:
            for r_exponent in (-100, -30, 0, 30, 36):
                if integer:
                    maximum = max(np.max(abs(values.real)), np.max(abs(values.imag)))
                    scaled = (np.rint(values.real/maximum*x_exponent)
                              + 1j*np.rint(values.imag/maximum*x_exponent))
                else:
                    scaled = values*2.**x_exponent
                args = (scaled, template*2.**r_exponent, 80_000.,
                        tuple(np.linspace(-4000, 4000, 21)), (0, 1, 2), 80)

                oracle = ExactColumns(geometry, None, args)
                oracle.full_grid = lambda *unused, current=oracle: full_grid(current)
                exact = full_grid(oracle)
                approximate = np.asarray(screen_grid(screen, geometry, *args))
                columns = np.asarray([0, 1, 39, 79])
                sparse = oracle(columns)
                np.testing.assert_array_equal(sparse.view(np.uint64),
                                              exact[:, columns].view(np.uint64))
                result = bound(geometry, args)
                delta = float(np.max(np.abs(approximate-exact)))
                if not result['eligible'] or delta > result['absolute_error']:
                    raise AssertionError((pattern, x_exponent, r_exponent, delta, result))
                if integer:
                    from interval_coarse_selection import select

                    residuals = args[3]
                    expected = acquisition._retain_score_map_peaks(
                        residuals, tuple(exact), 4, 4, 1000., args[-1])
                    selected = select(approximate, result['absolute_error'], residuals,
                                      4, 4, 1000., oracle)
                    if selected['retained'] != expected:
                        raise AssertionError('Integer screen selection differs from exact search')
                results.append(dict(pattern=pattern,
                                    sample_scale_exponent=None if integer else x_exponent,
                                    integer_maximum=x_exponent if integer else None,
                                    reference_scale_exponent=r_exponent,
                                    max_absolute_delta=delta, bound=result['absolute_error'],
                                    sparse_bit_exact=True, sparse_values=int(sparse.size)))
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    if pins != {p.name: digest(p) for p in files}:
        raise ValueError('Stress-check implementation changed')
    receipt = dict(cases=len(results), results=results, all_bounds_cover=True,
                   screen_kind=build.get('screen_kind', 'fp32'),
                   exact_selection_checked=integer,
                   all_sparse_bit_exact=True, source_pins=pins,
                   build_receipt_sha256=digest(candidate / 'screen-probe.json'),
                   started_utc_ns=began, ended_utc_ns=time.time_ns(),
                   production_qualified=False, scope='bounded synthetic stress check')
    fixture_tools.PROFILE.write_new(output, receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('results', 'source_pins')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private research output required')
    run(args.candidate.resolve(strict=True), args.output)
