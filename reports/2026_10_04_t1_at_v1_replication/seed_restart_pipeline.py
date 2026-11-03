"""Propagate improved full-data calibration initializations through T1-AT.

All N01--N16 scans independently; no heldout rows, location prior, or
truth-selected per-scan model. Preserve raw top-one GLRT observations, orbit
bank, timing priors/bounds, and greedy/replacement scoring. RX spline support
retains its quality gate. Calibration remains conditional on the known roof.
"""
import argparse
import copy
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import full_data_calibration as calibration
import full_data_localization as pilot
import full_scan_cohort as cohort
from refit_full_calibration_seeds import fixed_stationarity, OUT as PREFITS
from full_calibration_seed_audit import seed_vector
from post_scan_tle_localization import make_objective
from audit_post_scan_tle import diagnostics
from convergence_fisher import fit
from resume_position_convergence import best_record
from timing_bound_comparison import feasible_start, digest
from subset_positions import serial
from rf_calibration_diagnostic import CalibrationObjective

HERE = Path(__file__).resolve().parent
OUT = HERE/'full-scan-seed-restart'
OLD_CALIBRATION = calibration.OUT
OLD_POSITIONS = cohort.OUT
SCANS, ARMS = cohort.SCANS, cohort.ARMS
POST_BUDGET = dict(start_s=15., polish_s=20.)
POSITION_BUDGET = cohort.BUDGET.copy()


def configure():
    # Process-local adapter configuration; never rewrite archived inputs.
    calibration.OUT = OUT
    pilot.OUT = OUT


def fixed_objective(data, satellites, center, arm):
    obj = CalibrationObjective(data, data.initial, satellites, False, 60.)
    obj.center = center; obj.features = ((data.rf-center)/1e9)[:, None]
    obj.likelihood.features = obj.features
    obj.base.minimum_shift_s = max(obj.base.minimum_shift_s, -20.)
    obj.base.maximum_shift_s = min(obj.base.maximum_shift_s, 20.)
    if arm == 'zero-c': obj.bounds[-1] = (0., 0.)
    obj.base.deadline = float('inf')
    return obj


def check_rows(record, data):
    if record['fit_original_rows'] != data.original_rows.tolist() or record['evaluation_original_rows'] != data.original_rows.tolist():
        raise ValueError('Every passing top GLRT window must be fitted and evaluated')
    if record['heldout_original_rows']:
        raise ValueError('Unexpected heldout rows')


def unpack_fit(obj, record):
    value, kkt = fixed_stationarity(obj, record)
    np.testing.assert_allclose(value, record['objective'], atol=1e-7, rtol=0)
    return dict(parameters=np.asarray(record['parameters']), coefficient=record['coefficient'],
        vector=np.asarray(record['vector']), objective=value, success=bool(kkt <= 1e-3),
        nuisance_kkt=kkt, probability=obj.likelihood.last_result['row_association_probability'].copy())


def calibrate(scan):
    configure()
    data = calibration.load(calibration.INPUTS/scan/'seed-timing-v6')
    target = OUT/scan/'calibration.json'; target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        record = json.loads(target.read_text()); calibration.validate_scope(record, data)
        assert record['implementation_sha256'] == digest(Path(__file__))
        return record
    old_path = OLD_CALIBRATION/scan/'calibration.json'
    old = json.loads(old_path.read_text()); calibration.validate_scope(old, data)
    ids = np.asarray(old['satellite_indices']); center = old['rf_center_hz']
    pre, sources = {}, {}
    for arm in ARMS:
        path = PREFITS/f'{scan}-{arm}.json'; receipt = json.loads(path.read_text())
        check_rows(receipt, data)
        np.testing.assert_array_equal(receipt['seed_numbers'], data.numbers[ids])
        for source, sha in receipt['input_sources'].items(): assert digest(Path(source)) == sha
        obj = fixed_objective(data, ids, center, arm)
        pre[arm] = unpack_fit(obj, receipt['best'])
        assert pre[arm]['success'] and pre[arm]['objective'] <= old['pre'][arm]['objective']+1e-7
        sources[arm] = dict(path=str(path), sha256=digest(path))
    sys.path.insert(0, str(HERE.parent/'2026_10_03_ds13_coverage_goal'))
    import receiver_spline
    pred, visible = calibration.prediction(data, pre['fitted-c']['parameters'], ids,
                                          pre['fitted-c']['coefficient'], center)
    residual = calibration.circular(data.measured[:, None]-pred)
    support, winner = calibration.supported_rows(pre['fitted-c']['probability'], visible, residual)
    rows = np.arange(len(data.times))
    spline = receiver_spline.fit(data.times[support], data.receiver[support], residual[rows[support], winner[support]])
    correction = receiver_spline.predict(spline, data.times, data.receiver)
    adjusted = copy.copy(data); adjusted.measured = data.measured-correction
    arms = {}
    for arm in ARMS:
        obj = fixed_objective(adjusted, ids, center, arm)
        records = []
        for label, seed in [('improved-prefit', pre[arm]), ('previous-postfit', old['arms'][arm])]:
            start = seed_vector(obj, seed['parameters'], ids, seed['coefficient'])
            r = fit(obj, start, [0., 0.], POST_BUDGET['start_s'], True, radius_km=4.)
            r['stage'] = label; records.append(r)
        best = min(records, key=lambda r: r['objective'])
        r = fit(obj, np.asarray(best['vector']), [0., 0.], POST_BUDGET['polish_s'], True, radius_km=4.)
        r['stage'] = 'polish'; records.append(r)
        best = min(records, key=lambda r: r['objective'])
        result = unpack_fit(obj, best)
        arms[arm] = {k: v for k, v in result.items() if k != 'probability'}
        arms[arm].update(records=records, best=best)
        print('RESTART CALIBRATION', scan, arm, result['success'], 'spline support', int(sum(support)), flush=True)
    record = copy.deepcopy(old)
    record.update(scope=__doc__, implementation_sha256=digest(Path(__file__)),
        parent_calibration=dict(path=str(old_path), sha256=digest(old_path)), prefit_sources=sources,
        pre={a: {k: v for k, v in pre[a].items() if k != 'probability'} for a in ARMS}, arms=arms,
        correction_knots_hz=spline@receiver_spline.NULL.T, spline_training_rows=int(sum(support)),
        spline_training_original_rows=data.original_rows[support],
        converged=all(arms[a]['success'] for a in ARMS), postfit_budgets_s=POST_BUDGET,
        c_ablation='Same full windows, bootstrap bank, priors, postfit budgets and fitted-c-derived nonlinear RX correction.')
    target.write_text(json.dumps(record, default=serial, indent=2, allow_nan=False))
    if not record['converged']: raise RuntimeError('Unconverged calibration; do not proceed to association')
    return record


def upstream(scan):
    calibrate(scan)
    return calibration.associate(scan)


def remap_previous(record, old, new, shifts):
    return pilot.transferred(record, new, old, shifts)


def prepare(scan):
    configure()
    data, meta, original, archived, shifts = cohort.prepare(scan, 'full-rebuilt-members')
    old_path = OLD_POSITIONS/scan/'full-rebuilt-members.json'
    old_receipt = json.loads(old_path.read_text())
    with np.load(old_path.with_suffix('.npz')) as z:
        old_data = SimpleNamespace(**{k: z[k].copy() for k in z.files})
    assert old_receipt['input_sha256'] == digest(old_path.with_suffix('.npz'))
    # Transfer previous full-scan modes across the change in frozen RX baseline.
    old_calibration_record = json.loads((OLD_CALIBRATION/scan/'calibration.json').read_text())
    raw = calibration.load(calibration.INPUTS/scan/'seed-timing-v6')
    p = np.asarray(old_calibration_record['arms']['fitted-c']['parameters'])
    baseline = p[2+2*raw.receiver]+p[3+2*raw.receiver]*(raw.times-150.)
    for rx in (0, 1):
        mask = raw.receiver == rx
        baseline[mask] += np.interp(raw.times[mask], old_calibration_record['spline_nodes_s'],
                                   old_calibration_record['correction_knots_hz'][rx])
    lookup = {int(row): i for i, row in enumerate(raw.original_rows)}
    ix = np.array([lookup[int(row)] for row in data.original_rows])
    transfer = np.zeros(4)
    for rx in (0, 1):
        mask = data.receiver == rx
        x = np.column_stack([np.ones(sum(mask)), data.times[mask]-150.])
        transfer[2*rx:2*rx+2] = np.linalg.lstsq(x, baseline[ix][mask]-data.fixed_receiver_hz[mask], rcond=None)[0]
    return data, meta, original, archived, shifts, old_data, old_receipt, transfer


def position(scan):
    configure()
    target = OUT/'positions'/scan/'result.json'
    if target.exists():
        r = json.loads(target.read_text()); assert r['implementation_sha256'] == digest(Path(__file__))
        return str(target)
    data, meta, original, archived, shifts, previous_data, previous, transfer = prepare(scan)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = target.with_suffix('.npz')
    np.savez_compressed(source, **{k: getattr(data, k) for k in cohort.FIELDS})
    cal = calibration.FullCalibration(scan)
    result = dict(scope=__doc__, scan=scan, input_metadata=meta, input_sha256=digest(source),
        implementation_sha256=digest(Path(__file__)), maximum_budgets_s=POSITION_BUDGET,
        radius_km=4., total_timing_bound_s=20., fit_original_rows=data.original_rows,
        evaluation_original_rows=data.original_rows, heldout_original_rows=[], arms={},
        previous_position_source=dict(path=str(OLD_POSITIONS/scan/'full-rebuilt-members.json'),
                                      sha256=digest(OLD_POSITIONS/scan/'full-rebuilt-members.json')))
    for arm in ARMS:
        control_path = cohort.CONTROL/f'{scan}-{arm}-control.json'
        control = json.loads(control_path.read_text())
        fold_seed = pilot.transferred(control['best'], data, original, shifts)
        roof_seed = pilot.transferred(archived['arms'][arm]['roof'], data, original, shifts)
        previous_seed = remap_previous(previous['arms'][arm]['best'], previous_data, data, transfer)
        association_seed = dict(parameters=data.initial, coefficient=cal.record['arms'][arm]['coefficient'], point_km=[0., 0.])
        obj = make_objective(data, meta, arm); records = []
        def fitted(stage, seed, point, budget, fixed=False):
            r = fit(obj, feasible_start(obj, seed, 20., arm), point, budget, fixed, radius_km=4.)
            r['stage'] = stage; records.append(r); return r
        roofs = [fitted('roof-archived', roof_seed, [0., 0.], POSITION_BUDGET['roof'], True),
                 fitted('roof-association', association_seed, [0., 0.], POSITION_BUDGET['roof'], True)]
        roof = min(roofs, key=lambda r: r['objective'])
        probes = []
        for i, angle in enumerate(np.arange(4)*np.pi/2):
            probes.append(fitted(f'probe-{i}', roof, 3.2*np.array([np.cos(angle), np.sin(angle)]), POSITION_BUDGET['probe'], True))
        for i, seed in enumerate([roof, fold_seed, min(probes, key=lambda r: r['objective']), previous_seed]):
            fitted(f'search-{i}', seed, seed['point_km'], POSITION_BUDGET['search'])
        best = best_record(records)
        fitted('polish', best, best['point_km'], POSITION_BUDGET['polish'])
        best = best_record(records); values = diagnostics(obj, data, best)
        result['arms'][arm] = dict(best=best, roof=roof, records=records, **values)
        target.with_suffix('.partial.json').write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
        print('RESTART POSITION', scan, arm, round(values['distance_m']), values['converged'], flush=True)
    target.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
    return str(target)


def audit():
    configure()
    rows, coverages, calibration_checks = [], [], {}
    for scan in SCANS:
        cal = calibration.FullCalibration(scan)
        assert cal.record['implementation_sha256'] == digest(Path(__file__))
        calibration_checks[scan] = cohort.validate_calibration(cal)
        for info in [cal.record['parent_calibration'], *cal.record['prefit_sources'].values()]:
            assert digest(Path(info['path'])) == info['sha256']
        path = OUT/'positions'/scan/'result.json'; r = json.loads(path.read_text())
        data, meta, *_ = prepare(scan)
        cohort.validate_fit_scope(r, data)
        assert r['input_sha256'] == digest(path.with_suffix('.npz'))
        assert r['implementation_sha256'] == digest(Path(__file__))
        assert r['input_metadata'] == meta and r['maximum_budgets_s'] == POSITION_BUDGET
        with np.load(path.with_suffix('.npz')) as z:
            for key in cohort.FIELDS: np.testing.assert_array_equal(z[key], getattr(data, key))
        previous_path = Path(r['previous_position_source']['path'])
        assert digest(previous_path) == r['previous_position_source']['sha256']
        previous = json.loads(previous_path.read_text())
        assert previous['maximum_budgets_s'] == r['maximum_budgets_s']
        for arm in ARMS:
            obj = make_objective(data, meta, arm); metrics = diagnostics(obj, data, r['arms'][arm]['best'])
            for key, value in metrics.items(): np.testing.assert_allclose(value, r['arms'][arm][key], atol=1e-7, rtol=0)
            assert np.linalg.norm(r['arms'][arm]['best']['point_km']) <= 4.+1e-7
            assert max(abs(np.asarray(r['arms'][arm]['best']['parameters'])[6:])) <= 20.+1e-7
            if arm == 'zero-c': assert r['arms'][arm]['best']['coefficient'] == 0.
            for variant, receipt in [('previous-full-scan', previous), ('restarted-full-scan', r)]:
                v = receipt['arms'][arm]
                rows.append(dict(scan=scan, arm=arm, variant=variant,
                    windows=receipt['input_metadata']['window_count'], satellites=len(receipt['input_metadata']['numbers']),
                    **{k: v[k] for k in metrics}))
            for variant, root in [('previous-full-scan', OLD_CALIBRATION), ('restarted-full-scan', OUT)]:
                receipt = json.loads((root/scan/'associations'/f'{arm}.json').read_text()); a = receipt['final']
                assert a['denominator'] == len(cal.data.times)
                assert a['assigned'] == len(a['assignments']) == len({x['row_index'] for x in a['assignments']})
                coverages.append(dict(scan=scan, arm=arm, variant=variant, assigned=a['assigned'],
                    denominator=a['denominator'], coverage=a['assigned']/a['denominator'], satellites=a['satellites'],
                    association_rms_hz=float(np.sqrt(np.mean([x['residual_hz']**2 for x in a['assignments']]))),
                    converged=receipt['converged']))
    summaries = []
    for arm in ARMS:
        for variant in ('previous-full-scan', 'restarted-full-scan'):
            selected = [r for r in rows if (r['arm'], r['variant']) == (arm, variant)]
            errors = np.array([r['distance_m'] for r in selected])
            summaries.append(dict(arm=arm, variant=variant, scans=len(selected), below_1km=int(sum(errors < 1000)),
                median_error_m=float(np.median(errors)), mean_error_m=float(np.mean(errors)),
                converged=sum(r['converged'] for r in selected), boundary=sum(r['boundary'] for r in selected),
                median_posterior_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in selected]))))
    result = dict(status='passed', scope=__doc__, rows=rows, coverage=coverages, summaries=summaries,
        calibration_reconstructions=calibration_checks,
        caveats=['Known-roof calibration; this is not blind localization.',
                 'Raw GLRT, orbit bank, likelihood and priors unchanged; calibration initialization and resulting memberships change.',
                 'Both position RF arms share fitted-c-selected observations/bank, and search budgets match the preceding full-scan run.',
                 'Posterior-weighted residual RMS is fit quality, not independent coverage or localization evidence.',
                 'Best-found local 4 km solutions; convergence is not a global certificate.'])
    (OUT/'audit.json').write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
    for name, values in [('position-summary.csv', rows), ('association-summary.csv', coverages)]:
        with (OUT/name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0])); writer.writeheader(); writer.writerows(values)
    render(result)
    print(json.dumps(summaries, indent=2), flush=True)


def render(report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True)
    variants = ('previous-full-scan', 'restarted-full-scan')
    for column, arm in enumerate(ARMS):
        for i, scan in enumerate(SCANS):
            for row, source, key, scale in [(0, report['coverage'], 'coverage', 100.), (1, report['rows'], 'distance_m', 1.)]:
                ax = axes[row, column]
                pair = [next(r for r in source if (r['scan'], r['arm'], r['variant']) == (scan, arm, v)) for v in variants]
                ys = [scale*r[key] for r in pair]; ax.plot([i-.13, i+.13], ys, c='.7', lw=1)
                for j, (r, y, color) in enumerate(zip(pair, ys, ['#999999', '#0072b2'])):
                    x = i+(-.13 if j == 0 else .13)
                    ax.scatter(x, y, c=color, s=40, marker='^' if row == 1 and r['boundary'] else 'o',
                        label=['Previous full-data calibration', 'Improved-initialization full-data calibration'][j] if i == 0 and row == 0 else None)
                    if not r['converged']: ax.scatter(x, y, c='black', marker='x', s=50)
                if row == 1: ax.annotate(f'{ys[1]:.0f}', (i+.13, ys[1]), xytext=(0, 8), textcoords='offset points', ha='center', fontsize=8)
        axes[0, column].set_title('Fitted c' if arm == 'fitted-c' else 'c = 0')
        axes[0, column].set_ylabel('Associated top GLRT windows (%)'); axes[0, column].set_ylim(55, 105)
        axes[0, column].axhline(90, c='.5', ls=':')
        axes[1, column].set_ylabel('Best-found position error (m)'); axes[1, column].set_ylim(0, 4500)
        axes[1, column].axhline(1000, c='.4', ls='--'); axes[1, column].axhline(4000, c='.5', ls=':')
        axes[1, column].set_xticks(range(16), SCANS, rotation=45)
        stats = [next(r for r in report['summaries'] if (r['arm'], r['variant']) == (arm, v)) for v in variants]
        axes[1, column].set_title(f"Median {stats[0]['median_error_m']:.0f} → {stats[1]['median_error_m']:.0f} m; "
            f"below 1 km: {stats[0]['below_1km']} → {stats[1]['below_1km']} / 16")
    for ax in axes.ravel(): ax.grid(axis='y', alpha=.18); ax.set_axisbelow(True)
    axes[0, 0].legend(fontsize=8, loc='lower left')
    fig.suptitle('N01–N16 · does a better full-data calibration starting point improve localization?', fontsize=17)
    fig.text(.5, .02, 'Receiver spline, full-data postfit, exhaustive timing candidates and greedy + replacement rebuilt from improved prefits.\n'
        'No new heldouts. Same GLRT/TLEs/priors/±20 s timing bound. Known-roof calibration; independent 4 km position searches.\n'
        'Within each position RF pair: identical fitted-c-selected observations and bank. Triangles: boundary; ×: unconverged.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .11, 1, .95)); fig.savefig(OUT/'comparison.png', dpi=165); plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('stage', choices=['upstream', 'position', 'audit'])
    parser.add_argument('--scans', nargs='+', choices=SCANS, default=SCANS)
    args = parser.parse_args(); OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == 'audit': audit()
    else:
        function = upstream if args.stage == 'upstream' else position
        with ProcessPoolExecutor(max_workers=4) as pool:
            for f in as_completed([pool.submit(function, s) for s in args.scans]):
                print('COMPLETE', args.stage, f.result(), flush=True)
