"""Time an approximate coarse grid, returning only exact baseline scores to inference."""

import argparse
import importlib.util
import json
import os
import platform
import sys
import time
from pathlib import Path

import profile_algo07_glrt as fixture_tools
from stage_native_glrt_runtime import digest, verify, verify_files


def screen_grid(native, acquisition, values, template, rate, frequencies, symbols, epochs):
    import numpy as np

    starts = np.asarray([round(s * rate * acquisition.OFDM_SYMBOL_DURATION_S)
                         for s in symbols], dtype=np.intp)
    stops = np.asarray([round((s + 1) * rate * acquisition.OFDM_SYMBOL_DURATION_S)
                        for s in symbols], dtype=np.intp)
    period = rate / acquisition.FRAME_RATE_HZ
    offsets, frame = [], 0
    while (offset := round(frame * period)) < values.size:
        offsets.append(offset)
        frame += 1
    prefix = acquisition._power_prefix(values)
    rows = []
    for start in range(0, len(frequencies), 24):
        tile = frequencies[start:start + 24]
        padded = (*tile, *((tile[-1],) * (24 - len(tile))))
        grid = native.folded_anchor_score_grid(
            np.asarray(values, np.complex128), np.asarray(template, np.complex128),
            np.asarray(padded, dtype=float), starts, stops, np.asarray(offsets, np.intp),
            prefix, float(rate), epochs)
        rows.extend(grid[i] for i in range(len(tile)))
    return tuple(rows)


def run(candidate, fixture, output, *, selection=False, native_rescore=False, limit=None,
        computed_bound=False):
    import numpy as np

    output = output.resolve()
    if output.exists() or not output.is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private output required')
    build_path = candidate / 'screen-probe.json'
    build_pin = digest(build_path)
    script_pin = digest(Path(__file__))
    selector_path = Path(__file__).with_name('interval_coarse_selection.py')
    selector_pin = digest(selector_path) if selection else None
    oracle_path = Path(__file__).with_name('native_exact_columns.py')
    oracle_pin = digest(oracle_path) if native_rescore else None
    bound_path = Path(__file__).with_name('native_screen_bounds.py')
    bound_pin = digest(bound_path) if computed_bound else None
    if native_rescore and not selection:
        raise ValueError('Native rescoring requires selection diagnostics')
    if computed_bound and not selection:
        raise ValueError('Computed bounds require selection diagnostics')
    if limit is not None and limit <= 0:
        raise ValueError('Window limit must be positive')
    build = json.loads(build_path.read_text())
    base = Path(build['base'])
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    before = fixture_tools.PROFILE.verify(fixture / 'frozen.json')
    if not before['verified']:
        raise ValueError('Frozen input changed')
    fixture_tools.use_source(base)
    from leo.analysis.starlink import acquisition
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow, production_glrt

    extension = next((candidate / 'src/leo/analysis/starlink').glob('_native_acquisition*.so'))
    spec = importlib.util.spec_from_file_location('_screen._native_acquisition', extension)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    if native.folded_anchor_score_grid_backend() != 'avx2_fma':
        raise ValueError('This research probe requires AVX2/FMA')
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    original_grid = acquisition._folded_anchor_score_grid_native
    original_retain = acquisition._retain_score_map_peaks
    calls, latest = [], None

    def checked(*args, **kwargs):
        nonlocal latest
        if kwargs:
            raise ValueError('Unexpected backend override')
        implementations = [('baseline', lambda: original_grid(*args)),
                           ('screen', lambda: screen_grid(native, acquisition, *args))]
        if len(calls) % 2:
            implementations.reverse()
        results, seconds, cpu_seconds = {}, {}, {}
        for name, function in implementations:
            began, cpu_began = time.perf_counter(), time.process_time()
            results[name] = function()
            seconds[name] = time.perf_counter() - began
            cpu_seconds[name] = time.process_time() - cpu_began
        baseline, screen = np.asarray(results['baseline']), np.asarray(results['screen'])
        if baseline.shape != screen.shape or not np.isfinite(screen).all():
            raise ValueError('Nonfinite or mis-shaped screening scores')
        row = dict(shape=list(baseline.shape), samples=len(args[0]),
                   sample_rate_hz=args[2], order=[x[0] for x in implementations],
                   seconds=seconds, cpu_seconds=cpu_seconds,
                   maximum_absolute_delta=float(np.max(np.abs(screen - baseline))),
                   row_argmax_mismatches=int(np.sum(
                       np.argmax(screen, axis=1) != np.argmax(baseline, axis=1))))
        calls.append(row)
        latest = (results['baseline'], results['screen'], row, args)
        # Approximate values NEVER enter the actual acquisition/refinement path.
        return results['baseline']

    def retain(residuals, rows, count, epoch_separation, cfo_separation, epochs):
        began = time.perf_counter()
        baseline = original_retain(residuals, rows, count, epoch_separation,
                                   cfo_separation, epochs)
        baseline_selection_seconds = time.perf_counter() - began
        if latest is None or rows is not latest[0]:
            raise ValueError('Unbound coarse selection diagnostic')
        screen = original_retain(residuals, latest[1], count, epoch_separation,
                                 cfo_separation, epochs)
        latest[2].update(retained_count=len(baseline),
                         baseline_selection_seconds=baseline_selection_seconds,
                         retained_coordinates_equal=[x[1:] for x in baseline] ==
                         [x[1:] for x in screen],
                         exact_retained=[[float(x[0]), int(x[1]), float(x[2])]
                                         for x in baseline])
        if selection:
            from interval_coarse_selection import select

            exact_grid = np.asarray(rows)
            screen_scores = np.asarray(latest[1])
            checks = []
            bound_seconds = 0.
            if computed_bound:
                from native_screen_bounds import bound

                began = time.perf_counter()
                bound_result = bound(acquisition, latest[3])
                bound_seconds = time.perf_counter() - began
                latest[2]['bound'] = bound_result
                if not bound_result['eligible']:
                    raise ValueError('Computed-bound diagnostic requires eligible input')
                errors = (bound_result['absolute_error'],)
            else:
                errors = (1e-5, 1e-4)
            for assumed_error in errors:
                if np.max(np.abs(exact_grid - screen_scores)) > assumed_error:
                    raise ValueError('Diagnostic interval does not cover this measured grid')
                setup_began = time.perf_counter()
                oracle = None
                if native_rescore:
                    from native_exact_columns import ExactColumns

                    oracle = ExactColumns(acquisition, original_grid, latest[3])
                setup_seconds = time.perf_counter() - setup_began
                oracle_seconds, validation_seconds = 0., 0.

                def exact(columns, current_oracle=oracle):
                    nonlocal oracle_seconds, validation_seconds
                    if current_oracle is None:
                        return exact_grid[:, columns]
                    began = time.perf_counter()
                    values = current_oracle(columns)
                    oracle_seconds += time.perf_counter() - began
                    began = time.perf_counter()
                    np.testing.assert_array_equal(values.view(np.uint64),
                                                  exact_grid[:, columns].view(np.uint64))
                    validation_seconds += time.perf_counter() - began
                    return values

                began = time.perf_counter()
                result = select(screen_scores, assumed_error, residuals, count,
                                epoch_separation, cfo_separation, exact)
                selector_seconds = time.perf_counter() - began - validation_seconds
                if result['retained'] != baseline:
                    raise ValueError('Interval selector differs from complete baseline')
                checks.append(dict(assumed_error=assumed_error, selector_seconds=selector_seconds,
                                   exact_columns=result['exact_columns'], total_columns=epochs,
                                   requests=result['requests'], fallback=result['fallback'],
                                   selected_peaks_exact=True, native_rescoring_timed=native_rescore,
                                   setup_seconds=setup_seconds,
                                   bound_seconds=bound_seconds,
                                   error_source=('input-derived candidate bound' if computed_bound
                                                 else 'assumed diagnostic envelope'),
                                   native_rescore_seconds=oracle_seconds,
                                   validation_seconds_excluded=validation_seconds,
                                   native_calls=oracle.native_calls if oracle else None,
                                   dense_fallback_calls=(oracle.dense_fallback_calls
                                                         if oracle else None),
                                   error_bound_certified=False))
            latest[2]['selection_diagnostics'] = checks
        return baseline

    acquisition._folded_anchor_score_grid_native = checked
    acquisition._retain_score_map_peaks = retain
    all_windows = json.loads((fixture / 'input.json').read_text())['windows']
    windows = all_windows if limit is None else all_windows[:limit]
    started = time.time_ns()
    try:
        for item in windows:
            window = VerifiedFastWindow(item['sequence'], item['iq_sha256'], item['acquisition'],
                                        item['target'], np.load(fixture / item['samples'],
                                                               allow_pickle=False),
                                        item['sample_rate_hz'])
            receivers = production_glrt(window, tuple(item['receiver_ids']))
            expected = {p['receiver_id']: p['candidates'] for p in item['expected_probes']}
            if not all(fixture_tools.published_candidates(r) == expected[r.receiver_id]
                       for r in receivers):
                raise ValueError('Exact baseline path changed')
    finally:
        acquisition._folded_anchor_score_grid_native = original_grid
        acquisition._retain_score_map_peaks = original_retain
    verify(base, build['base_pin'])
    verify_files(candidate, build['files_sha256'])
    after = fixture_tools.PROFILE.verify(fixture / 'frozen.json')
    if not after['verified'] or digest(build_path) != build_pin:
        raise ValueError('Bound inputs or implementation changed')
    if (digest(Path(__file__)) != script_pin or
            (selection and digest(selector_path) != selector_pin) or
            (native_rescore and digest(oracle_path) != oracle_pin) or
            (computed_bound and digest(bound_path) != bound_pin)):
        raise ValueError('Diagnostic implementation changed during execution')
    totals = {key: sum(r['seconds'][key] for r in calls) for key in ['baseline', 'screen']}
    summary = dict(fixture=str(fixture), windows=len(windows), calls=len(calls),
                   fixture_windows=len(all_windows), native_rescoring_timed=native_rescore,
                   computed_bound=computed_bound,
                   totals=totals, grid_speedup=totals['baseline'] / totals['screen'],
                   maximum_absolute_delta=max(r['maximum_absolute_delta'] for r in calls),
                   row_argmax_mismatches=sum(r['row_argmax_mismatches'] for r in calls),
                   retained_coordinate_mismatch_calls=sum(
                       not r['retained_coordinates_equal'] for r in calls),
                   baseline_published_candidates_exact=True,
                   approximate_scores_used_for_inference=False,
                   error_bound_certified=False, production_modified=False)
    receipt = dict(summary=summary, calls=calls, fixture_before=before, fixture_after=after,
                   source_bytes_verified=True, build_receipt_sha256=build_pin,
                   script_sha256=script_pin, selector_sha256=selector_pin, oracle_sha256=oracle_pin,
                   bound_sha256=bound_pin,
                   cpu_affinity=cpu, cprofile=False, command=[sys.executable, *sys.argv],
                   python=sys.version, numpy=np.__version__, host=platform.node(),
                   threads={k: os.environ.get(k) for k in
                            ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
                   started_utc_ns=started, ended_utc_ns=time.time_ns(),
                   scope=('grid and selection diagnostic; exact native rescoring'
                          if native_rescore else 'grid diagnostic; exact baseline-array lookup'),
                   candidate_inference=False)
    fixture_tools.PROFILE.write_new(output, receipt)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection', action='store_true',
                        help='Test selection using assumed intervals and saved exact scores')
    parser.add_argument('--native-rescore', action='store_true',
                        help='Evaluate requested columns with the deployed native FP64 kernel')
    parser.add_argument('--limit', type=int,
                        help='Bound a diagnostic to the first N frozen windows')
    parser.add_argument('--computed-bound', action='store_true',
                        help='Use the input-derived candidate error bound, not assumed envelopes')
    args = parser.parse_args()
    run(args.candidate.resolve(strict=True), args.fixture.resolve(strict=True), args.output,
        selection=args.selection, native_rescore=args.native_rescore, limit=args.limit,
        computed_bound=args.computed_bound)
