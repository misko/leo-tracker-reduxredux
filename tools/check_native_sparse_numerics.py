"""Compare actual batched native columns bitwise with complete deployed grids."""

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import profile_algo07_glrt as fixture_tools
from check_native_screen_numerics import full_grid
from native_exact_columns import ExactColumns
from stage_native_glrt_runtime import digest, verify, verify_files


def run(candidate, output):
    build_file = candidate/'sparse-probe.json'
    pin = digest(build_file)
    build = json.loads(build_file.read_text())
    base = Path(build['base'])
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    files = [Path(__file__).with_name(n) for n in
             ('check_native_sparse_numerics.py', 'native_exact_columns.py',
              'check_native_screen_numerics.py')]
    pins = {p.name: digest(p) for p in files}
    fixture_tools.use_source(base)
    from leo.analysis.starlink import acquisition

    extension = next((candidate/'src/leo/analysis/starlink').glob('_native_acquisition*.so'))
    spec = importlib.util.spec_from_file_location('_sparse._native_acquisition', extension)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    if native.folded_anchor_score_grid_backend() != 'avx2_fma':
        raise RuntimeError('This explicit native stress check requires AVX2/FMA hardware')
    g = SimpleNamespace(OFDM_SYMBOL_DURATION_S=.0001, FRAME_RATE_HZ=1000,
                        _power_prefix=acquisition._power_prefix,
                        _native_acquisition=acquisition._native_acquisition,
                        _folded_anchor_score_grid_backend=acquisition._folded_anchor_score_grid_backend,
                        _constant_grid_step=acquisition._constant_grid_step)
    rng = np.random.default_rng(20261103)
    template = rng.normal(size=64)+1j*rng.normal(size=64)
    source = rng.normal(size=512)+1j*rng.normal(size=512)
    patterns = [('noise', source), ('zero-tail', np.r_[source[:250], np.zeros(262)]),
                ('constant', np.ones(512)*(1-1j))]
    results = []
    for name, values in patterns:
        for count in (1, 8, 11, 12, 21, 25):
            for x, r in ((-100, -100), (0, 0), (100, 100)):
                args = (values*2.**x, template*2.**r, 80_000.,
                        tuple(np.linspace(-4000, 4000, count)), (0, 1, 2), 80)
                oracle = ExactColumns(g, None, args,
                                      columns_native=native.folded_anchor_score_columns)
                oracle.full_grid = lambda *a, current=oracle: full_grid(current)
                expected = full_grid(oracle)
                columns = np.array([79, 0, 39, 79, 1], dtype=np.intp)
                sparse = oracle(columns)
                complete = oracle(np.arange(80, dtype=np.intp))
                np.testing.assert_array_equal(sparse.view(np.uint64),
                                              expected[:, columns].view(np.uint64))
                np.testing.assert_array_equal(complete.view(np.uint64), expected.view(np.uint64))
                results.append(dict(pattern=name, frequencies=count, sample_exponent=x,
                                    reference_exponent=r,
                                    exact_values=int(sparse.size+complete.size),
                                    bit_exact=True, native_calls=oracle.native_calls))
    # Exercise the C boundary itself, not only the Python oracle's checks.
    native_args = (oracle.values, oracle.template, oracle.tiles[0][0], oracle.starts,
                   oracle.stops, oracle.offsets, oracle.prefix, oracle.rate, oracle.epochs)
    invalid = [np.array([-1], np.intp), np.array([80], np.intp), np.array([], np.intp),
               np.array([1.5]), np.array([[1]], np.intp)]
    for columns in invalid:
        try:
            native.folded_anchor_score_columns(*native_args, columns)
        except ValueError:
            pass
        else:
            raise AssertionError('Native sparse boundary accepted invalid columns')
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    if digest(build_file) != pin or pins != {p.name: digest(p) for p in files}:
        raise ValueError('Sparse stress sources changed')
    summary = dict(cases=len(results), exact_values=sum(r['exact_values'] for r in results),
                   all_bit_exact=True, native_rejections=len(invalid), production_modified=False)
    fixture_tools.PROFILE.write_new(output, dict(summary=summary, results=results,
                                                 source_pins=pins, build_sha256=pin))
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private research output required')
    run(args.candidate.resolve(strict=True), args.output)
