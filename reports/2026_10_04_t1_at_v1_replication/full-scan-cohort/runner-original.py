"""Matched whole-scan calibration/reassociation comparison for N01--N16.

No held-out calibration or localization rows. Keep original observations,
top-one rule, TLE bank, likelihood, timing priors/bounds and independent 4 km
searches. The RX spline retains the existing quality support gate. Calibration
is conditioned on the known roof, not a blind positioning experiment.
"""
import argparse
import copy
import csv
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

import full_data_localization as pilot
from full_data_calibration import FullCalibration, OUT as CALIBRATION, ARMS
from leave_one_satellite_out import HERE, load
from post_scan_tle_localization import make_objective
from audit_post_scan_tle import diagnostics
from convergence_fisher import fit
from resume_position_convergence import best_record
from timing_bound_comparison import digest, feasible_start
from subset_positions import serial

SCANS = tuple(f'N{i:02d}' for i in range(1, 17))
CASES = ('fold-control', 'full-rebuilt-members')
OUT = HERE / 'full-scan-cohort'
CONTROL = HERE / 'satellite-drift-localization/polished'
BUDGET = dict(roof=8., probe=.75, search=10., polish=30.)
FIELDS = ('times', 'measured', 'rf', 'receiver', 'channel', 'group', 'margin',
          'original_rows', 'owners', 'numbers', 'position', 'velocity', 'nodes',
          'initial', 'fixed_receiver_hz')


def association_root(meta, scan):
    """Resolve the archived source from its receipt, never an assumed run name."""
    path = Path(meta['association_source'])
    if path.name != 'fitted-c.json' or path.parent.name != scan:
        raise ValueError('Association receipt is not for this scan/fitted-c arm')
    if digest(path) != meta['association_sha256']:
        raise ValueError('Archived association source changed')
    return path.parent.parent


def prepare(scan, case):
    _, meta, _ = load(scan)
    previous_root = pilot.OLD_ASSOC
    # The pilot's directory constant predates N01/N02's separate attempt2 run.
    # Override only inside this process/call; do not edit historical scripts.
    try:
        pilot.OLD_ASSOC = association_root(meta, scan)
        result = pilot.prepare(scan, case)
    finally:
        pilot.OLD_ASSOC = previous_root
    data, information, old, previous, shifts = result
    path = Path(information['association_source'])
    receipt = json.loads(path.read_text())
    expected = sorted(a['row_index'] for a in receipt['final']['assignments'])
    if data.original_rows.tolist() != expected:
        raise ValueError('Localization input omits or adds assigned windows')
    information['association_sha256'] = digest(path)
    if len(data.group) != len(np.unique(data.group)):
        raise ValueError('More than one candidate per GLRT window')
    return result


def previous_case(scan, case, arm, fallback):
    """Warm-start only from the same case, selected by score rather than truth."""
    paths = [HERE/'fold-splice-audit/refits/polished'/scan/f'{case}.json',
             CALIBRATION/scan/f'{case}-position.json']
    for path in paths:
        if path.exists():
            r = json.loads(path.read_text())
            return r['arms'][arm]['best'], dict(path=str(path), sha256=digest(path))
    return fallback, None


def run(task):
    scan, case = task
    target = OUT/scan/f'{case}.json'
    if target.exists():
        r = json.loads(target.read_text())
        assert r['implementation_sha256'] == digest(Path(__file__))
        return str(target)
    data, meta, old, previous, shifts = prepare(scan, case)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = target.with_suffix('.npz')
    np.savez_compressed(source, **{k: getattr(data, k) for k in FIELDS})
    cal = FullCalibration(scan)
    result = dict(scope=__doc__, scan=scan, case=case, input_metadata=meta,
                  input_sha256=digest(source), implementation_sha256=digest(Path(__file__)),
                  maximum_budgets_s=BUDGET, radius_km=4., total_timing_bound_s=20.,
                  fit_original_rows=data.original_rows, evaluation_original_rows=data.original_rows,
                  heldout_original_rows=[], arms={})
    for arm in ARMS:
        control_path = CONTROL/f'{scan}-{arm}-control.json'
        control = json.loads(control_path.read_text())
        baseline_seed = pilot.transferred(control['best'], data, old, shifts)
        roof_seed = pilot.transferred(previous['arms'][arm]['roof'], data, old, shifts)
        association_seed = dict(parameters=data.initial,
                                coefficient=cal.record['arms'][arm]['coefficient'], point_km=[0., 0.])
        archived, archived_source = previous_case(scan, case, arm, baseline_seed)
        obj = make_objective(data, meta, arm)
        records = []

        def fitted(stage, seed, point, budget, fixed=False):
            r = fit(obj, feasible_start(obj, seed, 20., arm), point, budget, fixed, radius_km=4.)
            r['stage'] = stage
            records.append(r)
            return r

        roofs = [fitted('roof-archived', roof_seed, [0., 0.], BUDGET['roof'], True),
                 fitted('roof-association', association_seed, [0., 0.], BUDGET['roof'], True)]
        roof = min(roofs, key=lambda r: r['objective'])
        probes = []
        for i, angle in enumerate(np.arange(4)*np.pi/2):
            point = 3.2*np.array([np.cos(angle), np.sin(angle)])
            probes.append(fitted(f'probe-{i}', roof, point, BUDGET['probe'], True))
        ring = min(probes, key=lambda r: r['objective'])
        for i, seed in enumerate([roof, baseline_seed, ring, archived]):
            fitted(f'search-{i}', seed, seed['point_km'], BUDGET['search'])
        best = best_record(records)
        fitted('polish', best, best['point_km'], BUDGET['polish'])
        best = best_record(records)
        values = diagnostics(obj, data, best)
        assert abs(values['objective']-best['objective']) < 1e-7
        assert np.linalg.norm(best['point_km']) <= 4.+1e-7
        assert np.max(abs(np.asarray(best['parameters'])[6:])) <= 20.+1e-7
        if case == 'fold-control':
            assert values['objective'] <= control['objective']+1e-7
        result['arms'][arm] = dict(best=best, roof=roof, records=records, **values,
            control_seed_source=dict(path=str(control_path), sha256=digest(control_path)),
            archived_case_seed_source=archived_source)
        target.with_suffix('.partial.json').write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
        print('COHORT POSITION', scan, case, arm, round(values['distance_m']),
              values['converged'], 'kkt', round(values['kkt'], 5), flush=True)
    target.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
    return str(target)


def validate_fit_scope(result, data):
    rows = data.original_rows.tolist()
    if result['fit_original_rows'] != rows or result['evaluation_original_rows'] != rows:
        raise ValueError('All associated rows must be fitted and evaluated')
    if result['heldout_original_rows']:
        raise ValueError('Unexpected held-out rows')
    if result['input_metadata']['numbers'] != data.numbers.tolist():
        raise ValueError('Candidate bank changed')
    if set(result['arms']) != set(ARMS):
        raise ValueError('Missing matched RF ablation')


def audit(scans=SCANS):
    rows, coverage, summaries = [], [], []
    for scan in scans:
        cal = FullCalibration(scan)
        assert cal.record['implementation_sha256'] == digest(HERE/'full_data_calibration.py')
        _, old_meta, _ = load(scan)
        old_root = association_root(old_meta, scan)
        for variant, root in [('fold-control', old_root/scan),
                              ('full-rebuilt-members', CALIBRATION/scan/'associations')]:
            for arm in ARMS:
                path = root/f'{arm}.json'
                r = json.loads(path.read_text()); a = r['final']
                assert a['denominator'] == len(cal.data.times)
                assert len(a['assignments']) == a['assigned'] == len({x['row_index'] for x in a['assignments']})
                coverage.append(dict(scan=scan, case=variant, arm=arm,
                    assigned=a['assigned'], denominator=a['denominator'], coverage=a['assigned']/a['denominator'],
                    satellites=a['satellites'], association_rms_hz=float(np.sqrt(np.mean([x['residual_hz']**2 for x in a['assignments']]))),
                    converged=r['converged'], source_sha256=digest(path)))
        for case in CASES:
            path = OUT/scan/f'{case}.json'; r = json.loads(path.read_text())
            data, meta, _, _, _ = prepare(scan, case)
            validate_fit_scope(r, data)
            assert r['input_sha256'] == digest(path.with_suffix('.npz'))
            assert r['implementation_sha256'] == digest(Path(__file__))
            assert r['maximum_budgets_s'] == BUDGET
            assert meta == r['input_metadata']
            with np.load(path.with_suffix('.npz')) as arrays:
                for key in FIELDS: np.testing.assert_array_equal(arrays[key], getattr(data, key))
            for arm in ARMS:
                v = r['arms'][arm]
                for provenance in ('control_seed_source', 'archived_case_seed_source'):
                    source = v[provenance]
                    if source: assert digest(Path(source['path'])) == source['sha256']
                obj = make_objective(data, meta, arm)
                metrics = diagnostics(obj, data, v['best'])
                for k, value in metrics.items():
                    np.testing.assert_allclose(value, v[k], atol=1e-7, rtol=0, err_msg=f'{scan}/{case}/{arm}/{k}')
                if arm == 'zero-c': assert v['best']['coefficient'] == 0.
                rows.append(dict(scan=scan, case=case, arm=arm, windows=len(data.times), satellites=len(data.numbers), **metrics))
    for case in CASES:
        for arm in ARMS:
            subset = [r for r in rows if (r['case'], r['arm']) == (case, arm)]
            errors = np.array([r['distance_m'] for r in subset])
            summaries.append(dict(case=case, arm=arm, scans=len(subset), below_1km=int(sum(errors < 1000)),
                median_error_m=float(np.median(errors)), mean_error_m=float(np.mean(errors)),
                converged=sum(r['converged'] for r in subset), boundary=sum(r['boundary'] for r in subset),
                median_posterior_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in subset]))))
    report = dict(status='passed', scope=__doc__, cases=len(rows), rows=rows, coverage=coverage,
                  summaries=summaries, known_roof_calibration=True, heldout_rows=[],
                  notes=['Position RF arms share fitted-c-selected raw observations and banks.',
                         'Association RF arms are separately selected from the same timing candidate pool.',
                         'Changing membership changes NLL normalization; do not compare absolute NLL across cases.',
                         'Same new optimizer budgets; archived same-case seeds retained when available.',
                         'A passed reconstruction audit is not a convergence or global-minimum certificate.'])
    (OUT/'audit.json').write_text(json.dumps(report, default=serial, indent=2, allow_nan=False))
    for name, values in [('position-summary.csv', rows), ('association-summary.csv', coverage)]:
        with (OUT/name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0])); writer.writeheader(); writer.writerows(values)
    print(json.dumps(summaries, indent=2), flush=True)
    render(report, scans)


def render(report, scans):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True)
    colors = ['#888888', '#0072b2']
    for col, arm in enumerate(ARMS):
        for i, scan in enumerate(scans):
            for row, values, key, scale in [(0, report['coverage'], 'coverage', 100.),
                                             (1, report['rows'], 'distance_m', 1.)]:
                ax = axes[row, col]
                pair = [next(v for v in values if (v['scan'], v['case'], v['arm']) == (scan, c, arm)) for c in CASES]
                ys = [scale*v[key] for v in pair]
                ax.plot([i-.13, i+.13], ys, c='.7', lw=1)
                for j, (v, y, color) in enumerate(zip(pair, ys, colors)):
                    x = i+(-.13 if j == 0 else .13)
                    marker = '^' if row == 1 and v['boundary'] else 'o'
                    ax.scatter(x, y, c=color, marker=marker, s=40,
                        label=['Stitched fold calibration', 'Full-scan calibration + rebuilt associations'][j] if i == 0 and row == 0 else None)
                    if not v['converged']: ax.scatter(x, y, marker='x', s=55, c='black')
                if row == 1:
                    ax.annotate(f'{ys[1]:.0f}', (i+.13, ys[1]), xytext=(0, 8), textcoords='offset points', ha='center', fontsize=8)
        axes[0, col].set_title('Fitted c' if arm == 'fitted-c' else 'c = 0')
        axes[0, col].set_ylabel('Associated top GLRT windows (%)'); axes[0, col].set_ylim(55, 105)
        axes[0, col].axhline(90, c='.5', ls=':')
        axes[1, col].set_ylabel('Best-found position error (m)'); axes[1, col].set_ylim(0, 4500)
        axes[1, col].axhline(1000, c='.4', ls='--'); axes[1, col].axhline(4000, c='.5', ls=':')
        axes[1, col].set_xticks(range(len(scans)), scans, rotation=45)
        stats = [next(s for s in report['summaries'] if (s['case'], s['arm']) == (c, arm)) for c in CASES]
        axes[1, col].set_title(f"Median {stats[0]['median_error_m']:.0f} → {stats[1]['median_error_m']:.0f} m; "
                              f"below 1 km: {stats[0]['below_1km']} → {stats[1]['below_1km']} / {len(scans)}")
    for ax in axes.ravel(): ax.grid(axis='y', alpha=.18); ax.set_axisbelow(True)
    axes[0, 0].legend(fontsize=9, loc='lower left')
    fig.suptitle('N01–N16 · replacing fold-specific receiver calibration with one full-scan fit', fontsize=18)
    fig.text(.5, .02, 'No new held-out folds. Same frozen refined top-one GLRT, TLEs, priors and ±20 s timing bounds. Independent 4 km searches.\n'
        'RX spline still uses quality-qualified support; calibration uses the known roof. Each position RF pair shares fitted-c-selected windows.\n'
        'Triangles: imposed boundary. ×: unconverged. Better coverage or frequency fit is not proof of better position accuracy.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .115, 1, .95)); fig.savefig(OUT/'comparison.png', dpi=165); plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--audit-only', action='store_true')
    parser.add_argument('--scans', nargs='+', default=SCANS, choices=SCANS)
    args = parser.parse_args(); OUT.mkdir(parents=True, exist_ok=True)
    if not args.audit_only:
        with ProcessPoolExecutor(max_workers=4) as pool:
            for f in as_completed([pool.submit(run, (s, c)) for s in args.scans for c in CASES]): f.result()
    audit(args.scans)
