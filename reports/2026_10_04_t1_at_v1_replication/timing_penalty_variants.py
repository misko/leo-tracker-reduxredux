"""Six matched timing-penalty experiments on N01--N16 full-data position inputs.

Original and both-tight controls; common-only tight, relative-only tight,
intermediate Gaussian, and a convex pseudo-Huber relative penalty. Fixed
zero-centered penalties chosen for the cohort before fitting, not per-scan
truth-based choices. Keep every assigned top-one window, the calibration,
satellite bank, likelihood, timing support and independent 4 km search disk.
Known-roof upstream calibration: in-sample development, not blind validation.
Scores choose local solutions; position truth only evaluates the result.
"""
import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

import full_data_timing_priors as previous
from timing_model import TimingObjective
from rf_calibration_diagnostic import CalibrationObjective
from convergence_fisher import fit
from resume_position_convergence import best_record
from audit_post_scan_tle import diagnostics
from timing_bound_comparison import feasible_start, digest
from subset_positions import serial

HERE = Path(__file__).resolve().parent
OUT = HERE/'timing-penalty-variants'
SEEDS = previous.OUT/'cross-start'
SCANS, ARMS = previous.SCANS, previous.ARMS
# sigmas are widths of penalties, not changes to hard bounds.
MODES = {
    'baseline': dict(common_sigma_s=10., relative_sigma_s=1., transition_s=None),
    'both-tight': dict(common_sigma_s=10./3., relative_sigma_s=1./3., transition_s=None),
    'relative-only': dict(common_sigma_s=10., relative_sigma_s=1./3., transition_s=None),
    'common-only': dict(common_sigma_s=10./3., relative_sigma_s=1., transition_s=None),
    'intermediate': dict(common_sigma_s=5., relative_sigma_s=.5, transition_s=None),
    'robust-relative': dict(common_sigma_s=10./3., relative_sigma_s=1./3., transition_s=1.),
}
LABELS = {'baseline': 'Original Gaussian', 'both-tight': 'Both tight (previous winner)',
          'relative-only': 'Relative timing tight only', 'common-only': 'Common timing tight only',
          'intermediate': 'Intermediate Gaussian', 'robust-relative': 'Robust relative timing'}
COLORS = dict(zip(MODES, ['#777777', '#D55E00', '#0072B2', '#009E73', '#E69F00', '#CC79A7']))
BUDGET = dict(roof_s=5., search_s=8., polish_s=20., polish_passes=2, cross_s=20., cross_passes=2)


def relative_terms(delta, sigma, transition=None):
    """Penalty, first and second derivatives in satellite-relative seconds."""
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError('Positive finite relative sigma required')
    delta = np.asarray(delta, float)
    if transition is None:
        return .5*(delta/sigma)**2, delta/sigma**2, np.full_like(delta, 1./sigma**2)
    if not np.isfinite(transition) or transition <= 0:
        raise ValueError('Positive finite transition required')
    z = delta/transition
    root = np.hypot(1., z)
    # Rationalized form retains precision near zero.
    value = (delta/sigma)**2/(root+1.)
    return value, delta/(sigma**2*root), 1./(sigma**2*root**3)


class PenaltyTimingObjective(TimingObjective):
    def __init__(self, *args, common_sigma_s, relative_sigma_s, transition_s=None, **kwargs):
        if not np.isfinite(common_sigma_s) or common_sigma_s <= 0:
            raise ValueError('Positive finite common sigma required')
        relative_terms(np.zeros(1), relative_sigma_s, transition_s)
        self.common_sigma_s = common_sigma_s
        self.relative_sigma_s = relative_sigma_s
        self.transition_s = transition_s
        super().__init__(*args, **kwargs)

    def penalty(self, vector):
        vector = np.asarray(vector)
        delta = self.basis@vector[7:]
        values, first, _ = relative_terms(delta, self.relative_sigma_s, self.transition_s)
        gradient = np.zeros_like(vector)
        gradient[6] = vector[6]/self.common_sigma_s**2
        gradient[7:] = self.basis.T@first
        value = .5*(vector[6]/self.common_sigma_s)**2+np.sum(values)
        return float(value), gradient

    def penalty_curvature(self, vector):
        h = np.zeros((len(vector), len(vector)))
        delta = self.basis@np.asarray(vector)[7:]
        _, _, second = relative_terms(delta, self.relative_sigma_s, self.transition_s)
        h[6, 6] = 1./self.common_sigma_s**2
        h[7:, 7:] = self.basis.T@(second[:, None]*self.basis)
        return h


class Objective(CalibrationObjective):
    def __init__(self, data, center, arm, mode):
        satellites = np.arange(len(data.numbers))
        super().__init__(data, data.initial, satellites, False, 60.)
        self.base = PenaltyTimingObjective(data, data.initial, satellites, self.likelihood, 200., **MODES[mode])
        self.center = center; self.features = ((data.rf-center)/1e9)[:, None]
        self.likelihood.features = self.features
        self.base.minimum_shift_s = max(self.base.minimum_shift_s, -20.)
        self.base.maximum_shift_s = min(self.base.maximum_shift_s, 20.)
        if arm == 'zero-c': self.bounds[-1] = (0., 0.)
        elif arm != 'fitted-c': raise ValueError('Unknown RF arm')

    def curvature(self, vector):
        h = super().curvature(vector)
        # Remove the legacy helper's original Gaussian, then add the exact
        # curvature of our prior. Robust curvature is generally NOT diagonal
        # in the zero-sum basis. Data Fisher terms remain untouched.
        h[6, 6] -= .01
        indices = np.arange(7, self.size)
        h[indices, indices] -= 1.
        h[:self.size, :self.size] += self.base.penalty_curvature(vector[:self.size])
        return h


def dependencies():
    return dict(previous.dependencies(), **{str(Path(__file__)): digest(Path(__file__))})


def make_objective(data, saved, arm, mode):
    return Objective(data, saved['input_metadata']['rf_center_hz'], arm, mode)


def seed_pool(scan):
    paths = [SEEDS/f'{scan}-{a}-{m}.json' for a in ARMS for m in previous.PRECISIONS]
    rows = [json.loads(p.read_text()) for p in paths]
    assert len({r['input_sha256'] for r in rows}) == 1
    return rows, {str(p): digest(p) for p in paths}


def initial(task):
    scan, arm, mode = task; target = OUT/'initial'/f'{scan}-{arm}-{mode}.json'
    data, saved, source = previous.load(scan)
    pool, sources = seed_pool(scan)
    if target.exists():
        r = json.loads(target.read_text())
        assert r['dependencies'] == dependencies() and r['seed_sources'] == sources
        return str(target)
    assert all(r['input_sha256'] == saved['input_sha256'] for r in pool)
    obj = make_objective(data, saved, arm, mode)
    seeds = [previous.reprice(obj, r['best'], arm, f"seed-{r['arm']}-{r['mode']}") for r in pool]
    records = list(seeds)
    def fitted(stage, seed, point, budget, fixed=False):
        r = fit(obj, feasible_start(obj, seed, 20., arm), point, budget, fixed, radius_km=4.)
        r['stage'] = stage; records.append(r); return r
    roofs = [fitted(f'roof-{a}', saved['arms'][a]['roof'], [0., 0.], BUDGET['roof_s'], True) for a in ARMS]
    roof = min(roofs, key=lambda r: r['objective'])
    ordered = sorted(seeds, key=lambda r: r['objective'])
    # A second geographically distinct discovered branch if one exists.
    second = next((r for r in ordered[1:] if np.linalg.norm(np.asarray(r['point_km'])-ordered[0]['point_km']) >= .1), ordered[1])
    for i, seed in enumerate([ordered[0], second, roof]):
        fitted(f'search-{i}', seed, seed['point_km'], BUDGET['search_s'])
    for i in range(BUDGET['polish_passes']):
        best = best_record(records)
        if diagnostics(obj, data, best)['converged']: break
        fitted(f'polish-{i}', best, best['point_km'], BUDGET['polish_s'])
    best = best_record(records)
    metrics = diagnostics(obj, data, best)
    assert metrics['objective'] <= min(s['objective'] for s in seeds)+1e-7
    info = previous.timing_and_gradient(obj, best)
    result = dict(scope=__doc__, scan=scan, arm=arm, mode=mode, prior=MODES[mode],
                  dependencies=dependencies(), seed_sources=sources, input_sha256=saved['input_sha256'],
                  source=str(source), source_sha256=digest(source), windows=len(data.times), numbers=data.numbers,
                  fit_original_rows=data.original_rows, evaluation_original_rows=data.original_rows,
                  heldout_original_rows=[], radius_km=4., common_bound_s=10., total_timing_bound_s=20.,
                  maximum_budgets_s=BUDGET, best=best, roof=roof, records=records, timing=info, **metrics)
    target.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
    print('VARIANT', scan, arm, mode, round(result['distance_m']), 'm', result['converged'], round(result['kkt'], 5), flush=True)
    return str(target)


def cross(task):
    scan, arm, mode = task; target = OUT/'final'/f'{scan}-{arm}-{mode}.json'
    paths = [OUT/'initial'/f'{scan}-{a}-{m}.json' for a in ARMS for m in MODES]
    sources = {str(p): digest(p) for p in paths}
    if target.exists():
        r = json.loads(target.read_text())
        assert r['dependencies'] == dependencies() and r['cross_sources'] == sources
        return str(target)
    pool = [json.loads(p.read_text()) for p in paths]
    r = next(z for z in pool if z['arm'] == arm and z['mode'] == mode)
    data, saved, _ = previous.load(scan)
    obj = make_objective(data, saved, arm, mode)
    seeds = [previous.reprice(obj, z['best'], arm, f"cross-{z['arm']}-{z['mode']}") for z in pool]
    r['cross_seed_gain_nll'] = r['objective']-min(z['objective'] for z in seeds)
    r['records'].extend(seeds)
    for attempt in range(BUDGET['cross_passes']):
        best = best_record(r['records'])
        if diagnostics(obj, data, best)['converged']: break
        new = fit(obj, np.asarray(best['vector']), best['point_km'], BUDGET['cross_s'], False, radius_km=4.)
        new['stage'] = f'cross-polish-{attempt}'; r['records'].append(new)
    best = best_record(r['records'])
    metrics = diagnostics(obj, data, best)
    assert metrics['objective'] <= min(z['objective'] for z in seeds)+1e-7
    r.update(best=best, timing=previous.timing_and_gradient(obj, best), cross_sources=sources, **metrics)
    target.write_text(json.dumps(r, default=serial, indent=2, allow_nan=False))
    print('FINAL', scan, arm, mode, round(r['distance_m']), 'm', r['converged'], round(r['kkt'], 5), flush=True)
    return str(target)


def audit(root, scans):
    rows, isolation = [], []
    for scan in scans:
        data, saved, source = previous.load(scan)
        pool, _ = seed_pool(scan)
        for arm in ARMS:
            old = saved['arms'][arm]['best']; vector = np.asarray(old['vector'])
            control = make_objective(data, saved, arm, 'baseline')
            value, gradient = control.evaluate(vector)
            np.testing.assert_allclose(value, old['objective'], atol=1e-7, rtol=0)
            cp, cg = control.base.penalty(vector[:control.size])
            ch = control.curvature(vector); prior_h = control.base.penalty_curvature(vector[:control.size])
            for mode in MODES:
                path = root/f'{scan}-{arm}-{mode}.json'; r = json.loads(path.read_text())
                assert r['dependencies'] == dependencies() and r['prior'] == MODES[mode]
                assert r['input_sha256'] == saved['input_sha256'] and r['source_sha256'] == digest(source)
                assert r['fit_original_rows'] == r['evaluation_original_rows'] == data.original_rows.tolist()
                assert not r['heldout_original_rows'] and r['numbers'] == data.numbers.tolist()
                assert r['maximum_budgets_s'] == BUDGET
                assert all(digest(Path(p)) == sha for p, sha in r['seed_sources'].items())
                if 'cross_sources' in r: assert all(digest(Path(p)) == sha for p, sha in r['cross_sources'].items())
                obj = make_objective(data, saved, arm, mode)
                j, g = obj.evaluate(vector)
                p, pg = obj.base.penalty(vector[:obj.size])
                np.testing.assert_allclose(j-value, p-cp, atol=1e-7, rtol=0)
                np.testing.assert_allclose(g-gradient, np.r_[pg-cg, 0.], atol=1e-7, rtol=0)
                expected_h = ch.copy()
                expected_h[:obj.size, :obj.size] += obj.base.penalty_curvature(vector[:obj.size])-prior_h
                np.testing.assert_allclose(obj.curvature(vector), expected_h, atol=1e-7, rtol=1e-14)
                assert obj.bounds == control.bounds
                assert obj.base.minimum_shift_s == control.base.minimum_shift_s
                assert obj.base.maximum_shift_s == control.base.maximum_shift_s
                checked = diagnostics(obj, data, r['best'])
                for k, v in checked.items(): np.testing.assert_allclose(v, r[k], atol=1e-7, rtol=0)
                assert r['objective'] <= min(s['objective'] for s in r['records'])+1e-7
                assert np.linalg.norm(r['best']['point_km']) <= 4.+1e-7
                assert abs(r['best']['vector'][6]) <= 10.+1e-7
                assert max(abs(np.asarray(r['best']['parameters'])[6:])) <= 20.+1e-7
                if arm == 'zero-c': assert r['best']['coefficient'] == 0.
                # Controls cannot discard any better solution from preceding runs.
                old_mode = {'baseline': 'baseline', 'both-tight': 'tighter'}.get(mode)
                if old_mode:
                    old_control = next(z for z in pool if z['arm'] == arm and z['mode'] == old_mode)
                    assert r['objective'] <= old_control['objective']+1e-7
                isolation.append(dict(scan=scan, arm=arm, mode=mode, penalty_only_objective_error=float(abs(j-value-p+cp))))
                rows.append(r)
    return rows, isolation


def summary(rows):
    lookup = {(r['scan'], r['arm'], r['mode']): r for r in rows}
    totals = []
    for arm in ARMS:
        for mode in MODES:
            selected = [r for r in rows if r['arm'] == arm and r['mode'] == mode]
            delta = np.array([r['distance_m']-lookup[r['scan'], arm, 'baseline']['distance_m'] for r in selected])
            dtight = np.array([r['distance_m']-lookup[r['scan'], arm, 'both-tight']['distance_m'] for r in selected])
            totals.append(dict(arm=arm, mode=mode, scans=len(selected),
                median_error_m=float(np.median([r['distance_m'] for r in selected])),
                mean_error_m=float(np.mean([r['distance_m'] for r in selected])),
                below_1km=sum(r['distance_m'] < 1000 for r in selected),
                converged_below_1km=sum(r['distance_m'] < 1000 and r['converged'] for r in selected),
                converged=sum(r['converged'] for r in selected), boundary=sum(r['boundary'] for r in selected),
                improved_vs_original=int(sum(delta < -1)), worsened_vs_original=int(sum(delta > 1)),
                improved_vs_both_tight=int(sum(dtight < -1)), worsened_vs_both_tight=int(sum(dtight > 1)),
                median_posterior_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in selected])),
                total_data_nll=float(sum(r['data_nll'] for r in selected)),
                median_common_timing_abs_s=float(np.median([abs(r['timing']['common_timing_s']) for r in selected])),
                median_relative_timing_rms_s=float(np.median([r['timing']['relative_timing_rms_s'] for r in selected]))))
    return totals


def render(root, rows, totals, scans):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    lookup = {(r['scan'], r['arm'], r['mode']): r for r in rows}
    fig, axes = plt.subplots(2, 1, figsize=(18, 10), sharex=True, sharey=True)
    for ax, arm in zip(axes, ARMS):
        for j, mode in enumerate(MODES):
            for i, scan in enumerate(scans):
                r = lookup[scan, arm, mode]; x = i+(j-2.5)*.115
                ax.scatter(x, r['distance_m'], s=32, color=COLORS[mode], marker='^' if r['boundary'] else 'o',
                           label=LABELS[mode] if i == 0 else None, zorder=3)
                if not r['converged']: ax.scatter(x, r['distance_m'], s=65, color='black', marker='x', zorder=4)
        ax.set_title('Fitted c' if arm == 'fitted-c' else 'c = 0', fontsize=13)
        ax.axhline(1000, color='.4', ls='--', lw=1); ax.axhline(4000, color='.5', ls=':', lw=1)
        ax.set_ylim(0, 4600); ax.grid(axis='y', alpha=.18); ax.set_ylabel('Best-found position error (m)')
    axes[0].legend(ncol=3, loc='upper left', fontsize=9)
    axes[1].set_xticks(range(len(scans)), scans)
    fig.suptitle('Timing penalties | isolate common shift, relative shifts and tail behavior', fontsize=18)
    fig.text(.5, .02, 'Same full-data penalty-10 associations, top-one windows, calibration and orbit bank. Every retained window fitted; no held-outs.\n'
             'Common timing +/-10 s; total satellite timing +/-20 s; independent 4 km position searches. Matched seed pools and maximum budgets.\n'
             'Triangles = boundary; crosses = unconverged. Known-roof calibration; local development results, not blind validation.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .955)); fig.savefig(root/'position-comparison.png', dpi=165); plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(17, 7), sharex=True)
    for axs, arm in zip(axes, ARMS):
        for mode in list(MODES)[2:]:
            r = [lookup[s, arm, mode] for s in scans]; ref = [lookup[s, arm, 'both-tight'] for s in scans]
            for ax, key in zip(axs, ['distance_m', 'posterior_weighted_residual_rms_hz']):
                ax.plot(range(len(scans)), [a[key]-b[key] for a, b in zip(r, ref)], marker='o', ms=3, color=COLORS[mode], label=LABELS[mode])
        for ax, label in zip(axs, ['Position error change (m)', 'Posterior-weighted RMS change (Hz)']):
            ax.axhline(0, color='.4', lw=1); ax.grid(alpha=.16); ax.set_ylabel(label)
            ax.set_title('Fitted c' if arm == 'fitted-c' else 'c = 0')
    axes[0, 0].legend(fontsize=8); axes[1, 0].set_xticks(range(len(scans)), scans, rotation=60)
    axes[1, 1].set_xticks(range(len(scans)), scans, rotation=60)
    fig.suptitle('New modifications versus both-tight Gaussian | lower is better', fontsize=17)
    fig.text(.5, .015, 'Identical input observations; posterior weights can change. Improved in-sample frequency fit does not establish better localization.\n'
             'See the position plot for boundary/convergence flags. Penalized objectives across different priors are not model evidence.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .11, 1, .95)); fig.savefig(root/'changes-vs-both-tight.png', dpi=165); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    delta = np.linspace(-4, 4, 501)
    for mode in ['baseline', 'intermediate', 'both-tight', 'robust-relative']:
        spec = MODES[mode]; p, g, _ = relative_terms(delta, spec['relative_sigma_s'], spec['transition_s'])
        axes[0].plot(delta, p, color=COLORS[mode], label=LABELS[mode]); axes[1].plot(delta, g, color=COLORS[mode])
    for ax in axes: ax.set_xlabel('Satellite-relative timing shift (s)'); ax.grid(alpha=.2)
    axes[0].set_ylabel('Relative timing penalty'); axes[1].set_ylabel('Penalty gradient per second')
    axes[0].legend(fontsize=8); fig.suptitle('What changes in the prior: robust tails limit the pull of large shifts')
    fig.tight_layout(); fig.savefig(root/'penalty-shapes.png', dpi=165); plt.close(fig)
    keys = ['scan', 'arm', 'mode', 'windows', 'distance_m', 'converged', 'boundary', 'objective', 'data_nll',
            'timing_prior_nll', 'posterior_weighted_residual_rms_hz', 'strong_soft_windows', 'kkt']
    flat = [dict(**{k: r[k] for k in keys}, **r['timing']) for r in rows]
    for name, values in [('comparison.csv', flat), ('summary.csv', totals)]:
        with (root/name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0])); writer.writeheader(); writer.writerows(values)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--scans', nargs='+', choices=SCANS, default=SCANS)
    parser.add_argument('--phase', choices=['initial', 'cross', 'render'], default='initial')
    parser.add_argument('--workers', type=int, default=8); args = parser.parse_args()
    for directory in [OUT/'initial', OUT/'final']: directory.mkdir(parents=True, exist_ok=True)
    if args.phase != 'render':
        runner = initial if args.phase == 'initial' else cross
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(runner, (s, a, m)) for s in args.scans for a in ARMS for m in MODES]
            for f in as_completed(jobs): f.result()
    root = OUT/'initial' if args.phase == 'initial' else OUT/'final'
    rows, isolation = audit(root, args.scans); totals = summary(rows)
    render(root, rows, totals, args.scans)
    receipt = dict(passed=True, scope=__doc__, cases=len(rows), scans=args.scans, modes=MODES,
                   summaries=totals, isolation_checks=isolation, dependencies=dependencies(),
                   maximum_budgets_s=BUDGET, all_inputs_scores_gradients_curvatures_verified=True)
    (root/'audit.json').write_text(json.dumps(receipt, default=serial, indent=2, allow_nan=False))
    print(json.dumps(totals, indent=2), flush=True)


if __name__ == '__main__':
    main()
