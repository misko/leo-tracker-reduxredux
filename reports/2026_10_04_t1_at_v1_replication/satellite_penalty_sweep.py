"""Change only the T1-AT satellite-count penalty on frozen full-data calibration.

N01--N16 independently, penalties 5/10/15, same timing candidate pools, GLRT
observations, coherence gates and three replacement passes. Refit positions on
all selected windows with the preceding four-start 4 km recipe and budgets.
Within each penalty, both position RF arms share fitted-c-selected inputs.
Known-roof calibration and in-sample selection: not blind validation.
"""
import argparse
import contextlib
import csv
import io
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import full_data_calibration as calibration
import full_data_localization as pilot
import full_scan_cohort as cohort
import seed_restart_pipeline as restart
from audit_post_scan_tle import diagnostics
from convergence_fisher import fit
from post_scan_tle_localization import make_objective
from resume_position_convergence import best_record
from subset_positions import serial
from timing_bound_comparison import digest, feasible_start

HERE = Path(__file__).resolve().parent
BASE = HERE/'full-scan-seed-restart'
OUT = HERE/'satellite-penalty-5-10-15'
SCANS, ARMS = cohort.SCANS, cohort.ARMS
PENALTIES = (5, 10, 15)
BUDGET = restart.POSITION_BUDGET.copy()


def implementation_hashes():
    # Preserve the exact completed-run source when correcting reporting only.
    paths = [Path(__file__), HERE/'satellite_penalty_sweep_run_v1.py']
    return {digest(p) for p in paths if p.exists()}


def configure(penalty):
    calibration.OUT = BASE
    pilot.OUT = OUT/f'penalty-{penalty}'


def engine():
    sys.path.insert(0, str(calibration.LEGACY))
    import greedy_pool_two_scans as historical
    sys.path.insert(0, str(historical.OLD))
    from greedy_restart_scan import compile_mode
    from penalty_replace_search import Search
    return compile_mode, Search


def validate_score(result, penalty):
    for stage in ('initial', 'final'):
        r = result[stage]
        if r['objective'] != r['assigned']-penalty*r['satellites']:
            raise ValueError('Wrong satellite penalty in score')
        if len(r['assignments']) != r['assigned'] or len({a['row_index'] for a in r['assignments']}) != r['assigned']:
            raise ValueError('Duplicate or missing assigned windows')
        if len(r['selected']) != r['satellites'] or len({a['catalog_number'] for a in r['assignments']}) != r['satellites']:
            raise ValueError('Selected satellite inventory mismatch')
    if result['final']['objective'] < result['initial']['objective']:
        raise ValueError('Replacement reduced the requested objective')


def associate(scan):
    configure(10)
    cal = calibration.FullCalibration(scan); d = cal.data
    source = BASE/scan/'associations/candidate-pool.json'
    pool = json.loads(source.read_text())
    assert pool['calibration_sha256'] == digest(cal.path)
    assert pool['original_rows'] == d.original_rows.tolist()
    assert [(m['catalog_number'], m['offset_s']) for m in pool['arms'][ARMS[0]]] == [
        (m['catalog_number'], m['offset_s']) for m in pool['arms'][ARMS[1]]]
    compile_mode, Search = engine()
    dependencies = [Path(__file__), calibration.LEGACY/'greedy_restart_scan.py',
                    calibration.LEGACY/'penalty_replace_search.py']
    for arm in ARMS:
        modes = [compile_mode(m, d.receiver, d.channel) for m in pool['arms'][arm]]
        old = json.loads((BASE/scan/'associations'/f'{arm}.json').read_text())
        for penalty in PENALTIES:
            target = OUT/f'penalty-{penalty}'/scan/'associations'/f'{arm}.json'
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                receipt = json.loads(target.read_text())
                assert receipt['implementation_sha256'] in implementation_hashes()
                assert receipt['source_sha256'] == digest(source)
                validate_score(receipt, penalty)
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                result = Search(modes, d.group, d.times, penalty=penalty, minimum=10, minspan=5.).run(3)
            for selected in result['final']['selected']:
                m = pool['arms'][arm][selected['mode_index']]
                assignments = [a for a in result['final']['assignments'] if a['catalog_number'] == selected['catalog_number']]
                ix = np.asarray([a['row_index'] for a in assignments], int)
                error, visible, _ = cal.residual(arm, m['satellite_index'], m['offset_s'])
                assert np.all(visible[ix]) and np.all(abs(error[ix]) <= 600.)
                np.testing.assert_allclose(error[ix], [a['residual_hz'] for a in assignments], atol=1e-6, rtol=0)
            for stage in ('initial', 'final'):
                r = result[stage]
                assert len({int(d.group[a['row_index']]) for a in r['assignments']}) == r['assigned']
                for a in r['assignments']: a['row_index'] = int(d.original_rows[a['row_index']])
                r.update(denominator=len(d.times), coverage=r['assigned']/len(d.times), unassigned=len(d.times)-r['assigned'])
                if penalty == 10:
                    # Reproduction control: changing the wrapper must not change T1-AT.
                    assert json.loads(json.dumps(r, default=serial)) == old[stage]
            result.update(scan=scan, arm=arm, penalty=penalty, scope=__doc__,
                source=str(source), source_sha256=digest(source),
                calibration_source=str(cal.path), calibration_sha256=digest(cal.path),
                implementation_sha256=digest(Path(__file__)),
                dependency_sha256={str(p): digest(p) for p in dependencies},
                limits=dict(tolerance_hz=600., minimum_windows=10, minspan_s=5., maxgap_s=5., replacement_passes=3),
                penalty10_reproduced=penalty == 10)
            validate_score(result, penalty)
            target.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
            print('ASSOCIATION', scan, arm, penalty, result['final']['assigned'], result['final']['satellites'], result['converged'], flush=True)
    return scan


def prepare(scan, penalty):
    configure(penalty)
    data, meta, original, archived, shifts = cohort.prepare(scan, 'full-rebuilt-members')
    # Reproduce the preceding full-data multistart recipe, not a new warm start
    # chosen from whichever penalty happened to localize best.
    previous_path = restart.OLD_POSITIONS/scan/'full-rebuilt-members.json'
    previous = json.loads(previous_path.read_text())
    with np.load(previous_path.with_suffix('.npz')) as z:
        previous_data = SimpleNamespace(**{k: z[k].copy() for k in z.files})
    assert previous['input_sha256'] == digest(previous_path.with_suffix('.npz'))
    old_cal = json.loads((restart.OLD_CALIBRATION/scan/'calibration.json').read_text())
    raw = calibration.load(calibration.INPUTS/scan/'seed-timing-v6')
    p = np.asarray(old_cal['arms']['fitted-c']['parameters'])
    baseline = p[2+2*raw.receiver]+p[3+2*raw.receiver]*(raw.times-150.)
    for rx in (0, 1):
        mask = raw.receiver == rx
        baseline[mask] += np.interp(raw.times[mask], old_cal['spline_nodes_s'], old_cal['correction_knots_hz'][rx])
    lookup = {int(r): i for i, r in enumerate(raw.original_rows)}
    ix = np.array([lookup[int(r)] for r in data.original_rows])
    transfer = np.zeros(4)
    for rx in (0, 1):
        mask = data.receiver == rx
        x = np.column_stack([np.ones(sum(mask)), data.times[mask]-150.])
        transfer[2*rx:2*rx+2] = np.linalg.lstsq(x, baseline[ix][mask]-data.fixed_receiver_hz[mask], rcond=None)[0]
    return data, meta, original, archived, shifts, previous_data, previous, transfer


def same_input(data, path):
    with np.load(path) as z:
        return all(np.array_equal(z[k], getattr(data, k)) for k in cohort.FIELDS)


def position(task):
    scan, penalty = task
    configure(penalty)
    target = OUT/f'penalty-{penalty}'/scan/'position.json'
    if target.exists():
        receipt = json.loads(target.read_text())
        assert receipt['implementation_sha256'] in implementation_hashes()
        return str(target)
    data, meta, original, archived, shifts, previous_data, previous, transfer = prepare(scan, penalty)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = target.with_suffix('.npz')
    np.savez_compressed(source, **{k: getattr(data, k) for k in cohort.FIELDS})
    base_path = BASE/'positions'/scan/'result.json'
    base_receipt = json.loads(base_path.read_text())
    result = dict(scope=__doc__, scan=scan, penalty=penalty, input_metadata=meta,
        input_sha256=digest(source), implementation_sha256=digest(Path(__file__)),
        maximum_budgets_s=BUDGET, radius_km=4., total_timing_bound_s=20.,
        fit_original_rows=data.original_rows, evaluation_original_rows=data.original_rows,
        heldout_original_rows=[], arms={}, reused_identical_input=False,
        baseline_source=str(base_path), baseline_sha256=digest(base_path))
    assert base_receipt['maximum_budgets_s'] == BUDGET
    identical = same_input(data, base_path.with_suffix('.npz'))
    if penalty == 10: assert identical
    if identical:
        result.update(arms=base_receipt['arms'], reused_identical_input=True)
        print('POSITION REUSE', scan, penalty, 'exact same input and search recipe', flush=True)
    else:
        cal = calibration.FullCalibration(scan)
        for arm in ARMS:
            control_path = cohort.CONTROL/f'{scan}-{arm}-control.json'
            control = json.loads(control_path.read_text())
            fold_seed = pilot.transferred(control['best'], data, original, shifts)
            roof_seed = pilot.transferred(archived['arms'][arm]['roof'], data, original, shifts)
            previous_seed = pilot.transferred(previous['arms'][arm]['best'], data, previous_data, transfer)
            association_seed = dict(parameters=data.initial, coefficient=cal.record['arms'][arm]['coefficient'], point_km=[0., 0.])
            obj = make_objective(data, meta, arm); records = []
            def fitted(stage, seed, point, budget, fixed=False):
                r = fit(obj, feasible_start(obj, seed, 20., arm), point, budget, fixed, radius_km=4.)
                r['stage'] = stage; records.append(r); return r
            roofs = [fitted('roof-archived', roof_seed, [0., 0.], BUDGET['roof'], True),
                     fitted('roof-association', association_seed, [0., 0.], BUDGET['roof'], True)]
            roof = min(roofs, key=lambda r: r['objective'])
            probes = [fitted(f'probe-{i}', roof, 3.2*np.array([np.cos(a), np.sin(a)]), BUDGET['probe'], True)
                      for i, a in enumerate(np.arange(4)*np.pi/2)]
            for i, seed in enumerate([roof, fold_seed, min(probes, key=lambda r: r['objective']), previous_seed]):
                fitted(f'search-{i}', seed, seed['point_km'], BUDGET['search'])
            best = best_record(records)
            fitted('polish', best, best['point_km'], BUDGET['polish'])
            best = best_record(records); values = diagnostics(obj, data, best)
            result['arms'][arm] = dict(best=best, roof=roof, records=records, **values)
            target.with_suffix('.partial.json').write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
            print('POSITION', scan, penalty, arm, round(values['distance_m']), values['converged'], flush=True)
    target.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
    return str(target)


def audit():
    rows = []
    for scan in SCANS:
        for penalty in PENALTIES:
            data, meta, *_ = prepare(scan, penalty)
            root = OUT/f'penalty-{penalty}'/scan
            receipt = json.loads((root/'position.json').read_text())
            assert receipt['implementation_sha256'] in implementation_hashes()
            assert receipt['input_sha256'] == digest(root/'position.npz')
            assert receipt['input_metadata'] == meta and same_input(data, root/'position.npz')
            assert receipt['maximum_budgets_s'] == BUDGET
            assert digest(Path(receipt['baseline_source'])) == receipt['baseline_sha256']
            cohort.validate_fit_scope(receipt, data)
            if receipt['reused_identical_input']:
                assert same_input(data, Path(receipt['baseline_source']).with_suffix('.npz'))
            for arm in ARMS:
                a = json.loads((root/'associations'/f'{arm}.json').read_text())
                validate_score(a, penalty)
                assert a['implementation_sha256'] in implementation_hashes()
                assert digest(Path(a['source'])) == a['source_sha256']
                assert digest(Path(a['calibration_source'])) == a['calibration_sha256']
                for p, h in a['dependency_sha256'].items():
                    if Path(p) == Path(__file__):
                        assert h in implementation_hashes()
                    else:
                        assert digest(Path(p)) == h
                obj = make_objective(data, meta, arm)
                v = receipt['arms'][arm]; metrics = diagnostics(obj, data, v['best'])
                for key, value in metrics.items(): np.testing.assert_allclose(value, v[key], atol=1e-7, rtol=0)
                assert np.linalg.norm(v['best']['point_km']) <= 4.+1e-7
                assert np.max(abs(np.asarray(v['best']['parameters'])[6:])) <= 20.+1e-7
                if arm == 'zero-c': assert v['best']['coefficient'] == 0.
                f = a['final']
                rows.append(dict(scan=scan, arm=arm, penalty=penalty, denominator=f['denominator'],
                    assigned=f['assigned'], satellites=f['satellites'], coverage=f['coverage'],
                    association_score=f['objective'], replacement_converged=a['converged'],
                    association_rms_hz=float(np.sqrt(np.mean([x['residual_hz']**2 for x in f['assignments']]))),
                    position_windows=len(data.times), position_satellites=len(data.numbers),
                    reused_identical_input=receipt['reused_identical_input'], **metrics))
    for row in rows:
        baseline = next(r for r in rows if (r['scan'], r['arm'], r['penalty']) == (row['scan'], row['arm'], 10))
        assert baseline['denominator'] == row['denominator']
        row['error_change_from_penalty10_m'] = row['distance_m']-baseline['distance_m']
        row['assigned_change_from_penalty10'] = row['assigned']-baseline['assigned']
        row['satellites_change_from_penalty10'] = row['satellites']-baseline['satellites']
    summaries = []
    for arm in ARMS:
        for penalty in PENALTIES:
            selected = [r for r in rows if (r['arm'], r['penalty']) == (arm, penalty)]
            summaries.append(dict(arm=arm, penalty=penalty, scans=len(selected),
                pooled_coverage_pct=100*sum(r['assigned'] for r in selected)/sum(r['denominator'] for r in selected),
                median_satellites=float(np.median([r['satellites'] for r in selected])),
                median_error_m=float(np.median([r['distance_m'] for r in selected])),
                mean_error_m=float(np.mean([r['distance_m'] for r in selected])),
                median_posterior_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in selected])),
                below_1km=sum(r['distance_m'] < 1000 for r in selected),
                converged=sum(r['converged'] for r in selected), boundary=sum(r['boundary'] for r in selected),
                improved_by_over_1m=sum(r['error_change_from_penalty10_m'] < -1 for r in selected),
                worsened_by_over_1m=sum(r['error_change_from_penalty10_m'] > 1 for r in selected),
                identical_input_scans=sum(r['reused_identical_input'] for r in selected)))
    report = dict(status='passed', scope=__doc__, rows=rows, summaries=summaries,
        audit_implementation_sha256=digest(Path(__file__)),
        accepted_runner_sha256=sorted(implementation_hashes()),
        baseline_audit=dict(path=str(BASE/'audit.json'), sha256=digest(BASE/'audit.json')),
        caveats=['Penalty is changed only in association, not in the localization likelihood.',
                 'Minimum lane support remains 10 coherent windows spanning 5 s; gap limit 5 s.',
                 'Both RF position arms use identical fitted-c-selected data for each penalty.',
                 'Across penalties, membership and candidate bank may change; NLLs are not directly comparable.',
                 'Same multistart recipe and budgets; known-roof upstream calibration, not blind validation.',
                 'Convergence is local and constrained to 4 km, not a global minimum certificate.'])
    (OUT/'audit.json').write_text(json.dumps(report, default=serial, indent=2, allow_nan=False))
    for name, values in [('comparison.csv', rows), ('summary.csv', summaries)]:
        with (OUT/name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0])); writer.writeheader(); writer.writerows(values)
    render(report)
    print(json.dumps(summaries, default=serial, indent=2), flush=True)


def render(report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = {5: '#0072b2', 10: '#777777', 15: '#d55e00'}
    rows = report['rows']
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True)
    for col, arm in enumerate(ARMS):
        top, bottom = axes[:, col]
        for i, scan in enumerate(SCANS):
            selected = [next(r for r in rows if (r['scan'], r['arm'], r['penalty']) == (scan, arm, p)) for p in PENALTIES]
            xx = i+np.array([-.22, 0., .22])
            top.plot(xx, [r['distance_m'] for r in selected], c='.8', lw=1)
            for x, r in zip(xx, selected):
                p = r['penalty']
                top.scatter(x, r['distance_m'], color=colors[p], s=42, marker='^' if r['boundary'] else 'o',
                            label=f'Penalty {p}' if i == 0 else None)
                if not r['converged']: top.scatter(x, r['distance_m'], marker='x', c='black', s=46)
                if p != 10:
                    bottom.bar(i+(-.19 if p == 5 else .19), r['error_change_from_penalty10_m'], width=.36, color=colors[p])
        top.set_title('Fitted c' if arm == 'fitted-c' else 'c = 0')
        top.set_ylabel('Best-found position error (m)'); top.set_ylim(0, 4350)
        top.axhline(1000, c='.4', ls='--'); top.axhline(4000, c='.5', ls=':')
        bottom.axhline(0, c='.3', lw=.8); bottom.set_ylabel('Error change vs penalty 10 (m)\nnegative = improvement')
        bottom.set_xticks(range(16), SCANS, rotation=45)
    limits = [r['error_change_from_penalty10_m'] for r in rows]
    for ax in axes[1]: ax.set_ylim(min(limits)-100, max(limits)+100)
    for ax in axes.ravel(): ax.grid(axis='y', alpha=.18); ax.set_axisbelow(True)
    axes[0, 0].legend(loc='upper left', ncol=3, fontsize=9)
    fig.suptitle('T1-AT full-data prototype · satellite penalty 5 vs 10 vs 15', fontsize=18)
    fig.text(.5, .02, 'S = assigned windows − penalty × selected satellites. Frozen full-data calibration and timing candidate pools.\n'
        'Same ±600 Hz gate, ≥10-window coherence rule, replacement budget, timing priors and independent 4 km search recipe.\n'
        'Triangles: boundary; ×: unconverged. RF position pairs share fitted-c-selected data. Known-roof calibration; in-sample analysis.',
        ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .95)); fig.savefig(OUT/'position-error-comparison.png', dpi=165); plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(16, 8), sharex=True)
    for col, arm in enumerate(ARMS):
        for p in PENALTIES:
            selected = [next(r for r in rows if (r['scan'], r['arm'], r['penalty']) == (s, arm, p)) for s in SCANS]
            for row, key, scale in [(0, 'coverage', 100), (1, 'satellites', 1)]:
                axes[row, col].plot(range(16), [r[key]*scale for r in selected], '.-', c=colors[p], label=f'Penalty {p}')
        axes[0, col].set_title('Fitted c' if arm == 'fitted-c' else 'c = 0')
        axes[0, col].set_ylabel('Associated windows (%)'); axes[0, col].set_ylim(75, 100)
        axes[1, col].set_ylabel('Selected satellites'); axes[1, col].set_xticks(range(16), SCANS, rotation=45)
    for ax in axes.ravel(): ax.grid(alpha=.18)
    axes[0, 0].legend(ncol=3, fontsize=9)
    fig.suptitle('Association effects of the satellite-count penalty · unchanged GLRT denominator', fontsize=17)
    fig.text(.5, .02, 'These are association coverage and model-size changes, not evidence of improved satellite identity or location accuracy.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .06, 1, .95)); fig.savefig(OUT/'coverage-and-satellites.png', dpi=165); plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('stage', choices=['associate', 'position', 'audit'])
    parser.add_argument('--scans', nargs='+', choices=SCANS, default=SCANS)
    args = parser.parse_args(); OUT.mkdir(exist_ok=True)
    if args.stage == 'audit': audit()
    else:
        jobs = args.scans if args.stage == 'associate' else [(s, p) for s in args.scans for p in PENALTIES]
        function = associate if args.stage == 'associate' else position
        with ProcessPoolExecutor(max_workers=4) as pool:
            for future in as_completed([pool.submit(function, task) for task in jobs]):
                print('COMPLETE', args.stage, future.result(), flush=True)
