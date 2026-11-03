"""Exercise the integrated selector and its full fallback on bounded synthetic inputs."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import profile_algo07_glrt as fixture_tools
from check_native_screen_numerics import full_grid
from native_exact_columns import ExactColumns
from stage_native_glrt_runtime import digest, verify, verify_files


def run(candidate, output):
    build_file = candidate / 'screened-detector.json'
    build_pin = digest(build_file)
    build = json.loads(build_file.read_text())
    verify(Path(build['base']), build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    files = [Path(__file__).with_name(n) for n in
             ('check_screened_detector_numerics.py', 'check_native_screen_numerics.py',
              'native_exact_columns.py')]
    pins = {p.name: digest(p) for p in files}
    fixture_tools.use_source(candidate)
    from leo.analysis.starlink import acquisition, coarse_screen

    geometry = SimpleNamespace(
        OFDM_SYMBOL_DURATION_S=.0001, FRAME_RATE_HZ=1000,
        _power_prefix=acquisition._power_prefix,
        _native_acquisition=acquisition._native_acquisition,
        _folded_anchor_score_grid_backend=acquisition._folded_anchor_score_grid_backend,
        _constant_grid_step=acquisition._constant_grid_step,
        _retain_score_map_peaks=acquisition._retain_score_map_peaks)
    rng = np.random.default_rng(20261103)
    source = rng.normal(size=512) + 1j*rng.normal(size=512)
    template = rng.normal(size=64) + 1j*rng.normal(size=64)
    patterns = [('noise', source), ('alternating', np.tile([1+1j, -1-1j], 256)),
                ('prefix-cancellation', np.r_[source[:256], source[256:]*2.**-40])]
    cases = [(name, values*2.**x, template*2.**r, x, r)
             for name, values in patterns
             for x in (-100, -30, 0, 30, 36) for r in (-100, -30, 0, 30, 36)]
    cases.append(('zero', np.zeros_like(source), template, 0, 0))
    cases.append(('zero-reference', source, np.zeros_like(template), 0, 0))
    results = []
    frequencies = tuple(np.linspace(-4000, 4000, 21))
    for name, values, reference, x, r in cases:
        args = (values, reference, 80_000., frequencies, (0, 1, 2), 80)
        oracle = ExactColumns(geometry, None, args)
        geometry._folded_anchor_score_grid = (
            lambda *unused, current=oracle: tuple(full_grid(current)))
        expected = np.asarray(geometry._folded_anchor_score_grid())
        retained = acquisition._retain_score_map_peaks(frequencies, tuple(expected), 3, 3, 800., 80)
        observed = []
        rows, selected = coarse_screen.acquire(geometry, args, frequencies, 3, 3, 800.,
                                               observer=observed.append)
        if retained != selected:
            raise AssertionError('Retained scientific tuples changed')
        actual = np.asarray(rows)
        for score, epoch, frequency in selected:
            index = frequencies.index(frequency)
            neighbors = slice(max(0, epoch-1), min(80, epoch+2))
            np.testing.assert_array_equal(actual[:, neighbors].view(np.uint64),
                                          expected[:, neighbors].view(np.uint64))
            assert actual[index, epoch] == score
            assert acquisition._refine_epoch(actual[index], epoch, 80) == acquisition._refine_epoch(
                expected[index], epoch, 80)
        if observed[0]['path'] == 'full':
            np.testing.assert_array_equal(actual.view(np.uint64), expected.view(np.uint64))
        results.append(dict(pattern=name, sample_scale=x, reference_scale=r,
                            exact=True, diagnostic=observed[0]))
    verify(Path(build['base']), build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    if digest(build_file) != build_pin or pins != {p.name: digest(p) for p in files}:
        raise ValueError('Checked implementation changed')
    summary = dict(cases=len(results), exact=True,
                   screened=sum(r['diagnostic']['path'] == 'screened' for r in results),
                   complete_fallback=sum(r['diagnostic']['path'] == 'full' for r in results),
                   production_modified=False)
    fixture_tools.PROFILE.write_new(output, dict(summary=summary, cases=results,
                                                 build_sha256=build_pin, sources=pins))
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private research output required')
    run(args.candidate.resolve(strict=True), args.output)
