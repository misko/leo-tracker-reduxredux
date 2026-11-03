"""Ten structural final-position experiments on frozen full-data N01--N16.

Independent 4 km searches. No new calibration, associations, observations or RF.
Full associated top-one windows in every arm; no held-out rows. Known-roof
upstream calibration and development-cohort evaluation, not blind validation.
One C1 reference and ten predeclared approaches, matched fitted-c/c=0 budgets.
"""
import argparse
import csv
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.special import gammaln, logsumexp

import position_score_sweep as previous
from convergence_fisher import fit
from polish_position_score_sweep import slsqp_fit
from position_direct import coordinate
from render_leave_one_satellite_out import check_stationarity
from soft_solvers import _parameter_map, _normal_matrix

HERE = Path(__file__).resolve().parent
OUT = HERE/'position-structure-study'
SCANS, ARMS = previous.SCANS, previous.ARMS
MODES = {
    'C1': 'Reference: unchanged soft Gaussian',
    'A01': 'Equal total weight per original satellite',
    'A02': 'Equal total weight per satellite/receiver',
    'A03': 'Equal weight per occupied satellite/RX/5 s bin',
    'A04': 'GLRT confidence weights, clipped 0.25--4',
    'A05': 'Wrapped Student-t4 frequency likelihood',
    'A06': '90% narrow + 10% broad Gaussian frequency mixture',
    'A07': 'Frozen original owner or clutter; no identity switching',
    'A08': 'Independent extra receiver slope priors, sigma 1 Hz/s',
    'A09': 'Relative receiver slope prior, sigma 1 Hz/s',
    'A10': 'Per-receiver quadratic drift, endpoint sigma 100 Hz',
}
BUDGET = dict(roof_s=2., search_starts=3, search_s=5., polish_s=10.,
              cross_fisher_s=12., cross_slsqp_s=8.)
SIGMA = 200.
ALIAS = 1./4.4e-6


def row_weights(data, mode):
    n = len(data.times)
    if mode == 'A01': labels = np.asarray(data.owners)[:, None]
    elif mode == 'A02': labels = np.column_stack([data.owners, data.receiver])
    elif mode == 'A03':
        labels = np.column_stack([data.owners, data.receiver, np.floor(data.times/5.)])
    else: labels = None
    if labels is not None:
        _, inverse, counts = np.unique(labels, axis=0, return_inverse=True, return_counts=True)
        weights = 1./counts[inverse]
    elif mode == 'A04':
        quality = np.asarray(data.margin, float)
        if np.any(~np.isfinite(quality)) or np.median(quality) <= 0:
            raise ValueError('Positive finite GLRT margins required')
        weights = np.clip(quality/np.median(quality), .25, 4.)
    else: weights = np.ones(n)
    return weights/np.mean(weights)


def density_terms(residual, mode, sigma=SIGMA, alias=ALIAS):
    """Wrapped log density, d log f/d prediction, positive IRLS precision.

    Student-t has df=4 and variance matched to the reference 200 Hz Gaussian.
    Five wrapped images omit less than 1e-12 probability at these fixed scales.
    A06 also matches the unwrapped variance: .9*100^2+.1*sqrt(310000)^2=200^2.
    """
    residual = np.asarray(residual, float)
    if mode == 'A05':
        scale = sigma/np.sqrt(2.)
        log_parts, gradients, precisions = [], [], []
        for image in range(-2, 3):
            r = residual+image*alias
            precision = 5./(4.*scale**2+r*r)
            log_parts.append(gammaln(2.5)-gammaln(2.)-.5*np.log(4*np.pi)-np.log(scale)
                             -2.5*np.log1p(r*r/(4.*scale**2)))
            gradients.append(r*precision); precisions.append(precision)
    else:
        components = [(.9, sigma*.5), (.1, sigma*np.sqrt(7.75))] if mode == 'A06' else [(1., sigma)]
        log_parts, gradients, precisions = [], [], []
        for fraction, width in components:
            for image in range(-1, 2):
                r = residual+image*alias
                log_parts.append(np.log(fraction)-np.log(width)-.5*np.log(2*np.pi)-.5*(r/width)**2)
                gradients.append(r/width**2); precisions.append(np.full_like(r, 1./width**2))
    stacked = np.stack(log_parts)
    log_density = logsumexp(stacked, axis=0)
    conditional = np.exp(stacked-log_density)
    return (log_density, np.sum(conditional*np.stack(gradients), axis=0),
            np.sum(conditional*np.stack(precisions), axis=0))


class SingleWindowLikelihood:
    """Exact single-observation specialization of the finite-set likelihood.

    Optional positive row weights define a composite/power likelihood, not an
    unweighted generative likelihood. Responsibilities remain true probabilities;
    weights affect objective/gradient/curvature, never probability reporting.
    """
    def __init__(self, data, features, mode):
        if len(np.unique(data.group)) != len(data.group):
            raise ValueError('This specialization requires one candidate per window')
        self.measured = np.asarray(data.measured)
        self.alias_hz = ALIAS
        self.detection_probability = .8/len(data.numbers)
        self.clutter_rate = 2.
        self.features = features
        self.coefficients = np.zeros(features.shape[1])
        self.mode = mode
        self.weights = row_weights(data, mode)
        self.owners = np.array([int(np.flatnonzero(data.numbers == n)[0]) for n in data.owners])
        self.last_result = None

    def evaluate(self, predicted, visible, *, sigma_hz, **unused):
        predicted = np.asarray(predicted)+(self.features@self.coefficients)[:, None]
        residual = (self.measured[:, None]-predicted+ALIAS/2)%ALIAS-ALIAS/2
        visible = np.asarray(visible, bool).copy()
        if self.mode == 'A07':
            visible &= np.arange(visible.shape[1])[None, :] == self.owners[:, None]
        log_density, density_gradient, precision = density_terms(residual, self.mode, sigma_hz)
        q, clutter = self.detection_probability, self.clutter_rate
        log_signal = np.where(visible, np.log(q/(1.-q))+log_density, -np.inf)
        log_sum_signal = logsumexp(log_signal, axis=1)
        log_sum = np.logaddexp(np.log(clutter/ALIAS), log_sum_signal)
        log_empty = -clutter+visible.sum(axis=1)*np.log1p(-q)
        per_window = log_empty+log_sum-np.log(-np.expm1(log_empty))
        probs = np.exp(log_signal-log_sum[:, None])
        result = dict(total_log_likelihood=float(self.weights@per_window),
            window_log_likelihood=per_window, row_association_probability=probs,
            prediction_gradient=self.weights[:, None]*probs*density_gradient,
            irls_weights=self.weights[:, None]*probs*precision,
            row_clutter_probability=1.-probs.sum(axis=1))
        self.last_result = result
        return result


class Objective(previous.Objective):
    def __init__(self, data, center, arm, mode):
        super().__init__(data, center, arm, previous.BASE)
        self.mode = mode
        if mode == 'A10':
            curve = ((data.times-150.)/150.)**2
            extras = np.column_stack([curve*(data.receiver == rx) for rx in (0, 1)])
            self.features = np.column_stack([self.features, extras])
            self.bounds += [(-500., 500.)]*2
            self.scale = np.r_[self.scale, [100., 100.]]
            self.initial = np.r_[self.initial, [0., 0.]]
        self.likelihood = SingleWindowLikelihood(data, self.features, mode)
        self.base.likelihood = self.likelihood
        self.base.deadline = float('inf')

    def extra_penalty(self, vector):
        v = np.asarray(vector)
        h = np.zeros((len(v), len(v)))
        if self.mode == 'A08': h[3, 3] = h[5, 5] = 1.
        elif self.mode == 'A09':
            h[3, 3] = h[5, 5] = 1.
            h[3, 5] = h[5, 3] = -1.
        elif self.mode == 'A10': h[-2, -2] = h[-1, -1] = 1./100.**2
        return float(.5*v@h@v), h@v, h

    def evaluate(self, vector):
        value, gradient = super().evaluate(vector)
        penalty, pg, _ = self.extra_penalty(vector)
        return value+penalty, gradient+pg

    def curvature(self, vector):
        v = np.asarray(vector[:self.size])
        _, _, jac = self.base.predict(v, with_jacobian=True)
        weights = self.likelihood.last_result['irls_weights']
        mapping = _parameter_map(self.base)
        h = np.zeros((len(vector), len(vector)))
        h[:self.size, :self.size] = mapping.T@_normal_matrix(jac, weights)@mapping+self.base.penalty_curvature(v)
        for column in range(self.features.shape[1]):
            physical = jac.transpose_multiply((weights*self.features[:, column, None]).ravel())
            cross = self.base.vector_gradient(physical, v)
            h[:self.size, self.size+column] = cross
            h[self.size+column, :self.size] = cross
        h[self.size:, self.size:] = self.features.T@(weights.sum(axis=1)[:, None]*self.features)
        return h+self.extra_penalty(vector)[2]


@lru_cache(maxsize=2)
def inputs(scan):
    data, saved, source, _, _ = previous.inputs(scan)
    paths = [previous.OUT/'polished'/f'{scan}-{arm}-{mode}.json' for arm in ARMS for mode in previous.SPECS]
    pool = [json.loads(p.read_text()) for p in paths]
    assert all(r['input_sha256'] == saved['input_sha256'] for r in pool)
    return data, saved, source, pool, {str(p): previous.digest(p) for p in paths}


def make_objective(data, saved, arm, mode):
    return Objective(data, saved['input_metadata']['rf_center_hz'], arm, mode)


def seed_vector(obj, seed, arm):
    v = previous.feasible_start(obj, seed, 20., arm)
    if obj.features.shape[1] > 1:
        old_extras = np.asarray(seed.get('vector', []))[obj.size+1:]
        v = np.r_[v, old_extras if len(old_extras) == 2 else [0., 0.]]
    v[:2] = coordinate(np.asarray(seed['point_km']))
    for i, (lo, hi) in enumerate(obj.bounds):
        if lo is not None: v[i] = max(lo, v[i])
        if hi is not None: v[i] = min(hi, v[i])
    return v


def reprice(obj, seed, arm, stage):
    v = seed_vector(obj, seed, arm)
    record = dict(vector=v, point_km=seed['point_km'], coefficient=float(v[obj.size]),
        parameters=obj.base.state(v[:obj.size])['parameters'], fixed_location=False, stage=stage)
    score, kkt = check_stationarity(obj, record, 4.)
    record.update(objective=score, kkt_residual=kkt, success=kkt <= 1e-3, status='repriced')
    return record


def metrics(obj, data, record):
    result = previous.diagnostics(obj, data, record)
    extra = obj.extra_penalty(np.asarray(record['vector']))[0]
    result['extra_prior_nll'] = extra
    result['data_nll'] -= extra
    result['mean_signal_posterior'] = float(obj.likelihood.last_result['row_association_probability'].sum(axis=1).mean())
    return result


def fitted(obj, seed, stage, budget, fixed=False):
    point = [0., 0.] if fixed else seed['point_km']
    r = fit(obj, np.array(seed['vector']), point, budget, fixed, radius_km=4.)
    r['coefficient'] = float(r['vector'][obj.size])
    r['stage'] = stage
    return r


def run(task):
    scan, arm, mode, stage = task
    target = OUT/stage/f'{scan}-{arm}-{mode}.json'
    data, saved, source, pool, hashes = inputs(scan)
    implementation = previous.digest(Path(__file__))
    if target.exists():
        r = json.loads(target.read_text())
        assert r['implementation_sha256'] == implementation and r['input_sha256'] == saved['input_sha256']
        return str(target)
    begun = time.monotonic()
    obj = make_objective(data, saved, arm, mode)
    if stage == 'initial':
        records = [reprice(obj, r['best'], arm, f'prior-{r["arm"]}-{r["mode"]}') for r in pool]
        roof_seeds = [reprice(obj, saved['arms'][a]['roof'], arm, f'roof-seed-{a}') for a in ARMS]
        roofs = [fitted(obj, s, 'roof', BUDGET['roof_s'], True) for s in roof_seeds]
        roof = min(roofs, key=lambda r: r['objective'])
        ordered = sorted(records, key=lambda r: r['objective'])
        second = next((r for r in ordered[1:] if np.linalg.norm(np.array(r['point_km'])-ordered[0]['point_km']) > .1), ordered[1])
        records += roofs
        for i, seed in enumerate([ordered[0], second, roof]):
            records.append(fitted(obj, seed, f'search-{i}', BUDGET['search_s']))
        best = previous.best_record(records)
        if not metrics(obj, data, best)['converged']:
            records.append(fitted(obj, best, 'polish', BUDGET['polish_s']))
        result = dict(scope=__doc__, scan=scan, arm=arm, mode=mode, label=MODES[mode],
            source=str(source), source_sha256=previous.digest(source), seed_sources=hashes,
            input_sha256=saved['input_sha256'], implementation_sha256=implementation,
            previous_dependencies=previous.dependencies(), maximum_budgets_s=BUDGET,
            fit_original_rows=data.original_rows, evaluation_original_rows=data.original_rows,
            heldout_original_rows=[], numbers=data.numbers, windows=len(data.times), radius_km=4.,
            weights=obj.likelihood.weights, roof=roof, records=records)
    else:
        paths = [OUT/'initial'/f'{scan}-{a}-{m}.json' for a in ARMS for m in MODES]
        cross_pool = [json.loads(p.read_text()) for p in paths]
        result = next(r for r in cross_pool if (r['arm'], r['mode']) == (arm, mode))
        records = list(result['records'])
        records += [reprice(obj, r['best'], arm, f'cross-{r["arm"]}-{r["mode"]}') for r in cross_pool]
        result['cross_sources'] = {str(p): previous.digest(p) for p in paths}
        for algorithm in ['fisher', 'slsqp']:
            best = previous.best_record(records)
            if metrics(obj, data, best)['converged']: break
            if algorithm == 'fisher': r = fitted(obj, best, 'cross-fisher', BUDGET['cross_fisher_s'])
            else:
                r = slsqp_fit(obj, best, BUDGET['cross_slsqp_s'])
                r['coefficient'] = float(r['vector'][obj.size])
                r['stage'] = 'cross-slsqp'
            records.append(r)
        result['records'] = records
    best = previous.best_record(records)
    reference = previous.objective(data, saved, arm, 'C1')
    common_seed = reprice(reference, best, arm, 'common-reference')
    common = previous.finish(reference, data, common_seed)
    result.update(best=best, **metrics(obj, data, best), stage=stage,
        common_reference_data_nll=common['data_nll'], elapsed_stage_s=time.monotonic()-begun)
    previous.save(target, result)
    print(stage.upper(), scan, arm, mode, round(result['distance_m']), 'm',
          'KKT', round(result['kkt'], 5), flush=True)
    return str(target)


def self_check():
    data, saved, _, pool, _ = inputs('N01')
    errors = []
    for arm in ARMS:
        ref = previous.objective(data, saved, arm, 'C1')
        obj = make_objective(data, saved, arm, 'C1')
        seed = next(r['best'] for r in pool if r['arm'] == arm and r['mode'] == 'C1')
        v = seed_vector(obj, seed, arm)
        j, g = obj.evaluate(v); j0, g0 = ref.evaluate(v)
        np.testing.assert_allclose(j, j0, atol=1e-7, rtol=0)
        np.testing.assert_allclose(g, g0, atol=2e-8, rtol=0)
        np.testing.assert_allclose(obj.curvature(v), ref.curvature(v), atol=1e-7, rtol=1e-9)
        for mode in MODES:
            obj = make_objective(data, saved, arm, mode)
            v = seed_vector(obj, seed, arm)
            v[3] += .03; v[5] -= .02
            if mode == 'A10': v[-2:] = [10., -20.]
            _, grad = obj.evaluate(v)
            for i in [0, 1, 2, 3, 5, 6, 7, obj.size, *range(obj.size+1, len(v))]:
                step = 1e-4 if i in (2, obj.size) or i > obj.size else 2e-5
                left, right = v.copy(), v.copy(); left[i] -= step; right[i] += step
                num = (obj.evaluate(right)[0]-obj.evaluate(left)[0])/(2*step)
                errors.append(abs(num-grad[i]))
                np.testing.assert_allclose(num, grad[i], atol=2e-3, rtol=2e-4,
                                           err_msg=f'{arm} {mode} index {i}')
    result = dict(status='passed', checks=len(errors), maximum_absolute_gradient_error=max(errors),
                  gaussian_control_score_gradient_curvature_parity=True)
    previous.save(OUT/'self-check.json', result)
    print(result, flush=True)


def csv_write(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def collect(stage):
    rows = []
    for scan in SCANS:
        data, saved, source, _, hashes = inputs(scan)
        for arm in ARMS:
            for mode in MODES:
                r = json.loads((OUT/stage/f'{scan}-{arm}-{mode}.json').read_text())
                assert r['input_sha256'] == saved['input_sha256'] and r['source_sha256'] == previous.digest(source)
                assert r['implementation_sha256'] == previous.digest(Path(__file__))
                assert r['previous_dependencies'] == previous.dependencies() and r['seed_sources'] == hashes
                assert r['maximum_budgets_s'] == BUDGET
                assert r['fit_original_rows'] == r['evaluation_original_rows'] == data.original_rows.tolist()
                assert not r['heldout_original_rows'] and r['numbers'] == data.numbers.tolist()
                obj = make_objective(data, saved, arm, mode)
                np.testing.assert_array_equal(r['weights'], obj.likelihood.weights)
                checked = metrics(obj, data, r['best'])
                for k, value in checked.items(): np.testing.assert_allclose(value, r[k], atol=1e-6, rtol=0)
                assert np.linalg.norm(r['best']['point_km']) <= 4.+1e-7
                v = np.asarray(r['best']['vector'])
                assert abs(v[6]) <= 10.+1e-7 and max(abs(np.asarray(r['best']['parameters'])[6:])) <= 20.+1e-7
                for z, (lo, hi) in zip(v, obj.bounds):
                    assert (lo is None or z >= lo-1e-7) and (hi is None or z <= hi+1e-7)
                if arm == 'zero-c': assert v[obj.size] == 0.
                assert r['best']['objective'] <= min(z['objective'] for z in r['records'])+1e-7
                rows.append(r)
    return rows


def report(stage):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = collect(stage)
    lookup = {(r['scan'], r['arm'], r['mode']): r for r in rows}
    summaries = []
    for arm in ARMS:
        for mode in MODES:
            subset = [lookup[s, arm, mode] for s in SCANS]
            errors = np.array([r['distance_m'] for r in subset])
            change = errors-np.array([lookup[s, arm, 'C1']['distance_m'] for s in SCANS])
            summaries.append(dict(arm=arm, mode=mode, label=MODES[mode], median_error_m=float(np.median(errors)),
                mean_error_m=float(np.mean(errors)), p90_error_m=float(np.percentile(errors, 90)),
                below_1km=int(sum(errors < 1000)), converged=sum(r['converged'] for r in subset),
                boundary=sum(r['boundary'] for r in subset), improved=int(sum(change < -1)), worsened=int(sum(change > 1)),
                median_paired_change_m=float(np.median(change)),
                posterior_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in subset])),
                owner_rms_hz=float(np.median([r['owner_rms_hz'] for r in subset])),
                mean_signal_posterior=float(np.mean([r['mean_signal_posterior'] for r in subset]))))
    target = OUT/stage
    csv_write(target/'summary.csv', summaries)
    keys = ['scan','arm','mode','windows','distance_m','converged','boundary','kkt','objective','data_nll',
            'timing_prior_nll','extra_prior_nll','owner_rms_hz','posterior_weighted_residual_rms_hz',
            'mean_signal_posterior','strong_changed_owner_windows','common_reference_data_nll']
    csv_write(target/'per-scan.csv', [{k:r[k] for k in keys} for r in rows])
    modes = ['C1']+[r['mode'] for r in sorted(summaries, key=lambda r:r['median_error_m']) if r['arm']=='fitted-c' and r['mode']!='C1']
    fig, axes = plt.subplots(1, 2, figsize=(19, 9), sharey=True)
    for ax, arm in zip(axes, ARMS):
        array = np.array([[lookup[s, arm, m]['distance_m'] for s in SCANS] for m in modes])
        im = ax.imshow(array, vmin=0, vmax=4000, cmap='viridis_r', aspect='auto')
        for j, mode in enumerate(modes):
            for i, scan in enumerate(SCANS):
                r = lookup[scan, arm, mode]
                label = f'{r["distance_m"]/1000:.2f}'+('△' if r['boundary'] else '')+('×' if not r['converged'] else '')
                ax.text(i,j,label,ha='center',va='center',fontsize=6.8,color='white' if r['distance_m']>2200 else 'black')
        ax.set_xticks(range(16),SCANS,rotation=60); ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0')
    axes[0].set_yticks(range(len(modes)), [m+' '+MODES[m] for m in modes],fontsize=8)
    fig.colorbar(im,ax=axes.ravel().tolist(),fraction=.022,pad=.02,label='Position error (m)')
    fig.suptitle('Ten structural approaches · independent N01–N16 position fits',fontsize=17)
    fig.subplots_adjust(left=.32,right=.92,bottom=.14,top=.9,wspace=.08)
    fig.text(.5,.025,'Numbers = km. △ = 4 km boundary; × = unconverged. Full data; frozen upstream inputs; matched RF arms and maximum budgets.\nDevelopment/in-sample comparison; bounded local search, not a global certificate.',ha='center',fontsize=9)
    fig.savefig(target/'position-errors.png',dpi=170);plt.close(fig)
    fig, axes = plt.subplots(1,2,figsize=(15,7),sharey=True)
    for ax, metric, title in zip(axes,['median_error_m','mean_error_m'],['Median position error','Mean position error']):
        for arm,shift,color in [('fitted-c',-.18,'#0072B2'),('zero-c',.18,'#D55E00')]:
            ax.barh(np.arange(len(modes))+shift,[next(r[metric] for r in summaries if r['arm']==arm and r['mode']==m) for m in modes],height=.35,color=color,label=arm)
        ax.set_title(title);ax.set_xlabel('Error (m)');ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    axes[0].set_yticks(range(len(modes)),[m+' '+MODES[m] for m in modes],fontsize=8);axes[0].invert_yaxis();axes[1].legend()
    fig.tight_layout();fig.savefig(target/'summary.png',dpi=170);plt.close(fig)
    audit=dict(status='passed',cases=len(rows),converged=sum(r['converged'] for r in rows),boundary=sum(r['boundary'] for r in rows),summary=summaries,
               checks='Inputs, settings, weights, scores, gradients/KKT and hard bounds reconstructed. All rows retained.')
    (target/'audit.json').write_text(json.dumps(audit,indent=2))
    print(json.dumps(audit,indent=2),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','check','initial','final','report'])
    parser.add_argument('--scans', nargs='+', default=SCANS, choices=SCANS)
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--stage', default='final', choices=['initial','final'])
    args = parser.parse_args()
    if args.action == 'prepare':
        previous.save(OUT/'protocol.json',dict(scope=__doc__,modes=MODES,baseline=previous.BASE,budgets=BUDGET,
            weights='All positive, frozen from metadata; normalize to mean 1; no discarded rows',
            likelihood='Exact one-observation finite-set specialization; Student-t and mixture match 200 Hz unwrapped variance',
            priors='A08/A09 concern extra residual slopes, not raw hardware slopes; A10 adds two RX quadratics, sigma 100 Hz, bounds +/-500 Hz',
            seed_source='All 36 preceding polished solutions per scan, in both RF arms',
            implementation_sha256=previous.digest(Path(__file__))))
    elif args.action == 'check': self_check()
    elif args.action == 'report': report(args.stage)
    else:
        jobs = [(s,a,m,args.action) for s in args.scans for m in MODES for a in ARMS]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(run,j) for j in jobs]): future.result()
