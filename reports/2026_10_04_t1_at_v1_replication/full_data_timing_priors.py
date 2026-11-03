"""Position-only timing-prior ablation on the frozen full-data penalty-10 inputs.

N01--N16 independently; all retained associated top-one GLRT windows fitted.
No new calibration, association, TLE, observation, visibility or position prior.
Uniform means constant density on the existing joint timing support, NOT an
improper unbounded prior. Gaussian widths change together, with fixed support.
Both RF arms and all four priors receive the same seed pool and maximum budgets.
Known-roof upstream calibration; in-sample, bounded local searches, not blind
validation or a certificate of the global minimum. Select solutions by their
own penalized likelihood, never by distance to truth. Compare data NLL separately
from location error; penalized scores across different priors are not evidence.
"""
import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from timing_prior_ablation import PriorObjective
from timing_bound_comparison import digest, feasible_start
from convergence_fisher import fit
from resume_position_convergence import best_record
from render_leave_one_satellite_out import check_stationarity
from audit_post_scan_tle import diagnostics
from subset_positions import serial
from position_direct import coordinate, coordinate_jacobian

HERE = Path(__file__).resolve().parent
SOURCE = HERE/'full-scan-seed-restart/positions'
OUT = HERE/'full-data-timing-priors'
SCANS = tuple(f'N{i:02}' for i in range(1, 17))
ARMS = ('fitted-c', 'zero-c')
PRECISIONS = {'baseline': 1., 'uniform': 0., 'wider': 1./9., 'tighter': 9.}
BUDGET = dict(roof=5., probe=.75, search=8., polish=15.)
LABELS = {'baseline': 'Current Gaussian', 'uniform': 'Uniform (bounded)',
          'wider': 'Wider Gaussian: sigma x3', 'tighter': 'Tighter Gaussian: sigma /3'}
COLORS = {'baseline': '#777777', 'uniform': '#CC79A7', 'wider': '#0072B2', 'tighter': '#D55E00'}


def specification(mode):
    precision = PRECISIONS[mode]
    return dict(precision=precision, common_sigma_s=10./np.sqrt(precision) if precision else None,
                relative_sigma_s=1./np.sqrt(precision) if precision else None,
                common_bound_s=10., total_satellite_bound_s=20., relative_sum_zero=True)


def dependencies():
    import inspect
    from timing_model import TimingObjective
    from rf_calibration_diagnostic import CalibrationObjective
    import finite_set_likelihood
    paths = [Path(__file__), HERE/'timing_prior_ablation.py', HERE/'convergence_fisher.py',
             HERE/'timing_bound_comparison.py', HERE/'audit_post_scan_tle.py',
             HERE/'render_leave_one_satellite_out.py', Path(inspect.getfile(TimingObjective)),
             Path(inspect.getfile(CalibrationObjective)), Path(inspect.getfile(finite_set_likelihood))]
    return {str(p): digest(p) for p in paths}


def load(scan):
    path = SOURCE/scan/'result.json'
    saved = json.loads(path.read_text())
    assert digest(path.with_suffix('.npz')) == saved['input_sha256']
    with np.load(path.with_suffix('.npz')) as z:
        data = SimpleNamespace(**{k: z[k].copy() for k in z.files})
    assert saved['fit_original_rows'] == saved['evaluation_original_rows'] == data.original_rows.tolist()
    assert not saved['heldout_original_rows']
    assert len(data.group) == len(np.unique(data.group))
    assert data.numbers.tolist() == saved['input_metadata']['numbers']
    for kind in ('association', 'calibration'):
        meta = saved['input_metadata']
        assert digest(Path(meta[f'{kind}_source'])) == meta[f'{kind}_sha256']
    return data, saved, path


def objective(data, saved, arm, mode):
    obj = PriorObjective(data, saved['input_metadata']['rf_center_hz'], arm, PRECISIONS[mode])
    obj.base.deadline = float('inf')
    return obj


def reprice(obj, seed, arm, stage):
    vector = feasible_start(obj, seed, 20., arm)
    vector[:2] = coordinate(np.asarray(seed['point_km']))
    r = dict(seed, vector=vector, coefficient=float(vector[-1]), stage=stage,
             parameters=obj.base.state(vector[:obj.size])['parameters'], fixed_location=False)
    value, kkt = check_stationarity(obj, r, 4.)
    r.update(objective=value, kkt_residual=kkt, success=kkt <= 1e-3, status='repriced-common-seed')
    return r


def timing_and_gradient(obj, record):
    vector = np.asarray(record['vector'])
    obj.base.deadline = float('inf')
    _, grad = obj.evaluate(vector)
    state = obj.base.state(vector[:obj.size])
    gradient = coordinate_jacobian(np.asarray(record['point_km'])).T @ grad[:2]
    return dict(common_timing_s=state['global_shift_s'],
                relative_timing_rms_s=float(np.sqrt(np.mean(state['individual_shifts_s']**2))),
                max_absolute_total_timing_s=float(np.max(abs(state['total_shifts_s']))),
                total_timing_boundary_count=int(sum(abs(state['total_shifts_s']) >= 19.999)),
                common_timing_boundary=bool(abs(state['global_shift_s']) >= 9.999),
                position_gradient_per_100m=(gradient*.1).tolist(),
                gradient_norm_per_100m=float(np.linalg.norm(gradient)*.1))


def run(task):
    scan, arm, mode = task
    target = OUT/f'{scan}-{arm}-{mode}.json'
    data, saved, path = load(scan)
    if target.exists():
        r = json.loads(target.read_text())
        assert r['dependencies'] == dependencies()
        assert r['input_sha256'] == saved['input_sha256'] and r['source_sha256'] == digest(path)
        return str(target)
    obj = objective(data, saved, arm, mode)
    seeds = [reprice(obj, saved['arms'][a]['best'], arm, f'seed-from-{a}') for a in ARMS]
    records = list(seeds)

    def fitted(stage, seed, point, budget, fixed=False):
        r = fit(obj, feasible_start(obj, seed, 20., arm), point, budget, fixed, radius_km=4.)
        r['stage'] = stage
        records.append(r)
        return r

    roofs = [fitted(f'roof-from-{a}', saved['arms'][a]['roof'], [0., 0.], BUDGET['roof'], True) for a in ARMS]
    roof = min(roofs, key=lambda r: r['objective'])
    ring = [fitted(f'probe-{i}', roof, 3.2*np.array([np.cos(angle), np.sin(angle)]), BUDGET['probe'], True)
            for i, angle in enumerate(np.arange(4)*np.pi/2)]
    starts = [roof, *seeds, min(ring, key=lambda r: r['objective'])]
    for i, seed in enumerate(starts):
        fitted(f'search-{i}', seed, seed['point_km'], BUDGET['search'])
    best = best_record(records)
    fitted('polish', best, best['point_km'], BUDGET['polish'])
    best = best_record(records)
    metrics = diagnostics(obj, data, best)
    assert metrics['objective'] <= min(s['objective'] for s in seeds)+1e-7
    assert np.linalg.norm(best['point_km']) <= 4.+1e-7
    assert np.max(abs(np.asarray(best['parameters'])[6:])) <= 20.+1e-7
    roof_info = timing_and_gradient(obj, roof)
    # Fixed-roof convergence concerns nuisance variables only, not position.
    roof_info['nuisance_converged'] = bool(roof['success'])
    result = dict(scope=__doc__, scan=scan, arm=arm, mode=mode, prior=specification(mode),
                  dependencies=dependencies(), source=str(path), source_sha256=digest(path),
                  input_sha256=saved['input_sha256'], windows=len(data.times), numbers=data.numbers,
                  fit_original_rows=data.original_rows, evaluation_original_rows=data.original_rows,
                  heldout_original_rows=[], radius_km=4., maximum_budgets_s=BUDGET,
                  previous_baseline_distance_m=saved['arms'][arm]['distance_m'],
                  best=best, roof=roof, records=records, roof_diagnostics=roof_info,
                  timing=timing_and_gradient(obj, best), **metrics)
    target.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
    print('TIMING', scan, arm, mode, round(metrics['distance_m']), 'm',
          'converged', metrics['converged'], 'KKT', round(metrics['kkt'], 6), flush=True)
    return str(target)


def collect(scans):
    rows = []
    for scan in scans:
        data, saved, path = load(scan)
        for arm in ARMS:
            control = objective(data, saved, arm, 'baseline')
            old = saved['arms'][arm]['best']
            np.testing.assert_allclose(control.evaluate(np.asarray(old['vector']))[0], old['objective'], atol=1e-7, rtol=0)
            for mode in PRECISIONS:
                r = json.loads((OUT/f'{scan}-{arm}-{mode}.json').read_text())
                assert r['dependencies'] == dependencies()
                assert r['source_sha256'] == digest(path) and r['input_sha256'] == saved['input_sha256']
                assert r['fit_original_rows'] == r['evaluation_original_rows'] == data.original_rows.tolist()
                assert not r['heldout_original_rows'] and r['numbers'] == data.numbers.tolist()
                assert r['maximum_budgets_s'] == BUDGET and r['prior'] == specification(mode)
                obj = objective(data, saved, arm, mode)
                checked = diagnostics(obj, data, r['best'])
                for key, value in checked.items():
                    np.testing.assert_allclose(value, r[key], atol=1e-7, rtol=0)
                assert r['best']['objective'] <= min(z['objective'] for z in r['records'])+1e-7
                assert np.linalg.norm(r['best']['point_km']) <= 4.+1e-7
                assert np.max(abs(np.asarray(r['best']['parameters'])[6:])) <= 20.+1e-7
                assert abs(float(r['best']['vector'][6])) <= 10.+1e-7
                if arm == 'zero-c': assert r['best']['coefficient'] == 0.
                if mode == 'uniform': assert r['timing_prior_nll'] == 0.
                rows.append(r)
    return rows


def summarize(rows):
    lookup = {(r['scan'], r['arm'], r['mode']): r for r in rows}
    summaries = []
    for arm in ARMS:
        for mode in PRECISIONS:
            selected = [r for r in rows if r['arm'] == arm and r['mode'] == mode]
            deltas = np.array([r['distance_m']-lookup[r['scan'], arm, 'baseline']['distance_m'] for r in selected])
            summaries.append(dict(arm=arm, mode=mode, scans=len(selected),
                median_error_m=float(np.median([r['distance_m'] for r in selected])),
                mean_error_m=float(np.mean([r['distance_m'] for r in selected])),
                below_1km=sum(r['distance_m'] < 1000 for r in selected),
                converged=sum(r['converged'] for r in selected), boundary=sum(r['boundary'] for r in selected),
                improved_over_1m=int(sum(deltas < -1)), worsened_over_1m=int(sum(deltas > 1)),
                median_posterior_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in selected])),
                total_data_nll=float(sum(r['data_nll'] for r in selected)),
                median_roof_gradient_per_100m=float(np.median([r['roof_diagnostics']['gradient_norm_per_100m'] for r in selected])),
                median_relative_timing_rms_s=float(np.median([r['timing']['relative_timing_rms_s'] for r in selected]))))
    return summaries


def render(rows, summaries, scans):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    lookup = {(r['scan'], r['arm'], r['mode']): r for r in rows}
    modes = list(PRECISIONS)
    fig, axes = plt.subplots(2, 1, figsize=(17, 9), sharex=True, sharey=True)
    for ax, arm in zip(axes, ARMS):
        medians = []
        for j, mode in enumerate(modes):
            values = [lookup[s, arm, mode] for s in scans]
            offset = (j-1.5)*.15
            for i, r in enumerate(values):
                ax.scatter(i+offset, r['distance_m'], color=COLORS[mode], s=40,
                           marker='^' if r['boundary'] else 'o', label=LABELS[mode] if i == 0 else None, zorder=3)
                if not r['converged']: ax.scatter(i+offset, r['distance_m'], color='black', marker='x', s=70, zorder=4)
            medians.append(f"{np.median([r['distance_m'] for r in values]):.0f}")
        ax.set_title(('Fitted c' if arm == 'fitted-c' else 'c = 0')+' | median error (current / uniform / wider / tighter): '+' / '.join(medians)+' m')
        ax.axhline(1000, color='.45', ls='--', lw=1); ax.axhline(4000, color='.45', ls=':', lw=1)
        ax.set_ylim(0, 4400); ax.set_ylabel('Best-found distance from roof (m)'); ax.grid(axis='y', alpha=.18)
    axes[0].legend(ncol=4, loc='upper left', fontsize=9)
    axes[-1].set_xticks(range(len(scans)), scans)
    fig.suptitle('Full-data T1-AT | change the timing prior, keep the inputs fixed', fontsize=18)
    fig.text(.5, .02, 'Same penalty-10 associations, top-one GLRT windows, full-scan RX calibration, TLE bank and maximum search budgets. No held-out rows.\n'
             'Bounds unchanged: common timing +/-10 s; total satellite timing +/-20 s; independent 4 km position disk.\n'
             'Triangles = boundary; crosses = unconverged. Known-roof calibration; best-found local results, not blind validation.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .95)); fig.savefig(OUT/'position-comparison.png', dpi=170); plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(17, 8), sharex=True)
    for axs, arm in zip(axes, ARMS):
        for mode in modes[1:]:
            values = [lookup[s, arm, mode] for s in scans]
            control = [lookup[s, arm, 'baseline'] for s in scans]
            series = [[r['distance_m']-b['distance_m'] for r, b in zip(values, control)],
                      [r['data_nll']-b['data_nll'] for r, b in zip(values, control)],
                      [r['posterior_weighted_residual_rms_hz']-b['posterior_weighted_residual_rms_hz'] for r, b in zip(values, control)]]
            for ax, ys in zip(axs, series):
                ax.plot(range(len(scans)), ys, marker='o', ms=3, color=COLORS[mode], label=LABELS[mode], alpha=.9)
        for ax, label in zip(axs, ['Position error change (m)', 'Data NLL change (no prior penalty)', 'Posterior-weighted RMS change (Hz)']):
            ax.axhline(0, color='.4', lw=1); ax.grid(alpha=.15); ax.set_ylabel(label)
            ax.set_title('Fitted c' if arm == 'fitted-c' else 'c = 0')
    for ax in axes[-1]: ax.set_xticks(range(len(scans)), scans, rotation=60)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle('Changes relative to the matched current-prior rerun | lower is better', fontsize=17)
    fig.text(.5, .02, 'Frequency fit and position accuracy are different outcomes. Compare data NLL, not penalized totals across different priors.\n'
             'RMS uses model-dependent association posteriors; inputs are identical, but effective weights may differ. See position plot for convergence flags.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .10, 1, .95)); fig.savefig(OUT/'fit-versus-position.png', dpi=165); plt.close(fig)
    keys = ['scan', 'arm', 'mode', 'windows', 'distance_m', 'converged', 'boundary', 'objective', 'data_nll',
            'timing_prior_nll', 'posterior_weighted_residual_rms_hz', 'strong_soft_windows', 'kkt', 'previous_baseline_distance_m']
    flat = [dict(**{k: r[k] for k in keys}, **r['timing'], roof_gradient_norm_per_100m=r['roof_diagnostics']['gradient_norm_per_100m'],
                 roof_nuisance_converged=r['roof_diagnostics']['nuisance_converged']) for r in rows]
    for name, values in [('comparison.csv', flat), ('summary.csv', summaries)]:
        with (OUT/name).open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(values[0])); w.writeheader(); w.writerows(values)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--scans', nargs='+', choices=SCANS, default=SCANS)
    p.add_argument('--workers', type=int, default=6); p.add_argument('--render-only', action='store_true')
    args = p.parse_args(); OUT.mkdir(exist_ok=True)
    if not args.render_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(run, (s, a, m)) for s in args.scans for a in ARMS for m in PRECISIONS]
            for f in as_completed(jobs): f.result()
    rows = collect(args.scans); summaries = summarize(rows)
    render(rows, summaries, args.scans)
    audit = dict(passed=True, scope=__doc__, cases=len(rows), scans=args.scans, summaries=summaries,
                 priors={m: specification(m) for m in PRECISIONS}, dependencies=dependencies(),
                 all_inputs_and_objectives_reconstructed=True, all_rows_fit_and_evaluated=True,
                 fixed_upstream_association_coverage=True, matched_rf_arms_and_search_budgets=True)
    (OUT/'audit.json').write_text(json.dumps(audit, default=serial, indent=2, allow_nan=False))
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == '__main__':
    main()
