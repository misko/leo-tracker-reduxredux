"""Challenge the pinned integer screen at its admitted arithmetic boundaries."""

import argparse
import ctypes
import importlib.util
import json
import platform
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import profile_algo07_glrt as fixtures
from check_native_screen_numerics import full_grid
from native_exact_columns import ExactColumns
from native_integer_screen import bound
from probe_native_screen import screen_grid
from stage_native_glrt_runtime import digest, verify, verify_files


def run(candidate, output):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise RuntimeError('Explicit Linux/x86-64 VNNI domain qualification required')
    build_file = candidate/'screen-probe.json'
    build_pin = digest(build_file)
    build = json.loads(build_file.read_text())
    if build.get('screen_kind') != 'integer_vnni':
        raise ValueError('Integer screen build required')
    base = Path(build['base'])
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    files = [Path(__file__).with_name(n) for n in
             ('check_integer_screen_domain.py', 'native_integer_screen.py',
              'native_screen_bounds.py', 'native_exact_columns.py',
              'check_native_screen_numerics.py', 'probe_native_screen.py')]
    pins = {p.name: digest(p) for p in files}
    if pins['native_integer_screen.py'] != build['transformer_sha256']:
        raise ValueError('Bound and native source are not the same qualified version')
    fixtures.use_source(base)
    from leo.analysis.starlink import acquisition

    extension = next((candidate/'src/leo/analysis/starlink').glob('_native_acquisition*.so'))
    spec = importlib.util.spec_from_file_location('_screen._native_acquisition', extension)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    if native.folded_anchor_score_grid_backend() != 'avx2_fma':
        raise RuntimeError('Explicit AVX-VNNI hardware required')
    g = SimpleNamespace(OFDM_SYMBOL_DURATION_S=.0001, FRAME_RATE_HZ=1000,
                        _power_prefix=acquisition._power_prefix,
                        _native_acquisition=acquisition._native_acquisition,
                        _folded_anchor_score_grid_backend=acquisition._folded_anchor_score_grid_backend,
                        _constant_grid_step=acquisition._constant_grid_step)
    # Each product, sum and cumulative prefix is an exactly representable integer.
    maximum_iq = np.full(1_000_000, 32767*(1+1j))
    prefix = acquisition._power_prefix(maximum_iq)
    expected = (np.arange(1_000_001, dtype=np.int64)*(2*32767**2)).astype(float)
    np.testing.assert_array_equal(prefix.view(np.uint64), expected.view(np.uint64))
    del maximum_iq, prefix, expected
    rows = []
    for taps in (1, 2, 44, 256, 4096):
        rate = taps*10_000.
        for maximum in (1, 127, 32767):
            qmax = min(32767., np.floor((2**31-1)/(2*taps*maximum)))-1
            for kind in ('coherent', 'quantization-tie', 'cancellation'):
                r = np.ones(taps, complex)*(1+1j)
                x = np.full(2*taps+128, maximum*(1+1j))
                if kind == 'quantization-tie':
                    r.imag = .5/(qmax/2)
                elif kind == 'cancellation':
                    x[1::2] *= -1
                for exponent in (-250, 0, 39):
                    args = (x, r*2.**exponent, rate, (0., rate*.1, -rate*.1), (0,), 64)
                    result = bound(g, args)
                    if not result['eligible']:
                        raise AssertionError(('Unexpected ineligible boundary', taps, kind, result))
                    oracle = ExactColumns(g, None, args)
                    exact = full_grid(oracle)
                    approximate = np.asarray(screen_grid(native, g, *args))
                    delta = float(np.max(abs(exact-approximate)))
                    if not np.isfinite(approximate).all() or delta > result['absolute_error']:
                        raise AssertionError(('Uncovered domain error', taps, maximum, kind,
                                              exponent, delta, result))
                    rows.append(dict(taps=taps, maximum_iq=maximum, reference_exponent=exponent,
                                     pattern=kind, delta=delta, bound=result['absolute_error'],
                                     maximum_int32_l1=2*taps*maximum*qmax,
                                     uses_full_fallback=result['absolute_error'] > .01))
    x = np.ones(512, complex)*(1+1j)
    args = x, np.ones(64, complex), 80_000., (0.,), (0,), 80
    invalid = []
    for name, values in [('fractional', x*.5), ('outside-int16', x*32768),
                         ('zero', x*0), ('nan', np.full_like(x, np.nan)),
                         ('infinite', np.full_like(x, np.inf))]:
        result = bound(g, (values, *args[1:]))
        if result['eligible']:
            raise AssertionError('Accepted unsupported IQ: '+name)
        invalid.append(dict(case=name, reason=result['reason']))
    libc = ctypes.CDLL(None)
    rounding = libc.fegetround()
    try:
        if libc.fesetround(0x400) != 0:
            raise RuntimeError('Cannot exercise FE_DOWNWARD on this qualified platform')
        result = bound(g, args)
        if result['eligible']:
            raise AssertionError('Non-nearest rounding was admitted')
        invalid.append(dict(case='FE_DOWNWARD', reason=result['reason']))
    finally:
        if libc.fesetround(rounding) != 0:
            raise RuntimeError('Failed to restore original rounding mode')
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    if digest(build_file) != build_pin or pins != {p.name: digest(p) for p in files}:
        raise ValueError('Domain-check implementation changed')
    summary = dict(cases=len(rows), covered=True, prefix_values_exact=1_000_001,
                   unsupported_rejected=len(invalid),
                   maximum_bound_fraction=max(r['delta']/r['bound'] for r in rows),
                   domain='pinned Linux/x86-64 integer screen; finite tests plus separate review',
                   production_modified=False)
    fixtures.PROFILE.write_new(output, dict(summary=summary, cases=rows, rejected=invalid,
                                             build_sha256=build_pin, source_pins=pins))
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private research output required')
    run(args.candidate.resolve(strict=True), args.output)
