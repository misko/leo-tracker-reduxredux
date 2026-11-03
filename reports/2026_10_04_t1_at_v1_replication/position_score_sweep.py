"""Sixteen final-score variants, two controls, frozen full-data N01--N16 inputs.

All scans independent. Same associated top-one windows, ephemerides, RX baseline,
satellite bank, hard bounds, seed pools and maximum search budgets in both RF arms.
This is in-sample development with known-roof upstream calibration, not validation.
Select positions by each objective, never by position error. Do not compare raw
NLL across different likelihood hyperparameters as localization evidence.
"""
import argparse
import csv
import html
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import numpy as np

import timing_penalty_variants as old
from rf_calibration_diagnostic import CalibrationObjective
from soft_solvers import _fisher_system
from convergence_fisher import fit
from resume_position_convergence import best_record
from audit_post_scan_tle import diagnostics
from timing_bound_comparison import feasible_start, digest
from subset_positions import serial

HERE = Path(__file__).resolve().parent
OUT = HERE/'position-score-sweep'
SCANS, ARMS = old.SCANS, old.ARMS
BASE = dict(sigma_hz=200., detection_budget=.8, clutter_rate=2.,
            common_sigma_s=10., relative_sigma_s=1./3.)
SPECS = {
    'C0': dict(BASE, relative_sigma_s=1.),
    'C1': BASE.copy(),
    'V01': dict(BASE, sigma_hz=75.),
    'V02': dict(BASE, sigma_hz=125.),
    'V03': dict(BASE, sigma_hz=300.),
    'V04': dict(BASE, detection_budget=.2),
    'V05': dict(BASE, detection_budget=1.6),
    'V06': dict(BASE, clutter_rate=.5),
    'V07': dict(BASE, clutter_rate=8.),
    'V08': dict(BASE, common_sigma_s=1.),
    'V09': dict(BASE, common_sigma_s=30.),
    'V10': dict(BASE, relative_sigma_s=.15),
    'V11': dict(BASE, relative_sigma_s=.6),
    'V12': dict(BASE, sigma_hz=125., relative_sigma_s=.15),
    'V13': dict(BASE, sigma_hz=125., clutter_rate=.5),
    'V14': dict(BASE, sigma_hz=125., clutter_rate=8.),
    'V15': dict(BASE, sigma_hz=300., relative_sigma_s=.15),
    'V16': dict(BASE, sigma_hz=125., detection_budget=1.6, clutter_rate=.5,
                common_sigma_s=3., relative_sigma_s=.15),
}
LABELS = {
    'C0': 'Original Gaussian control', 'C1': 'Tight-relative control',
    'V01': 'Frequency width 75 Hz', 'V02': 'Frequency width 125 Hz',
    'V03': 'Frequency width 300 Hz', 'V04': 'Detection budget 0.2',
    'V05': 'Detection budget 1.6', 'V06': 'Clutter rate 0.5',
    'V07': 'Clutter rate 8', 'V08': 'Common timing sigma 1 s',
    'V09': 'Common timing sigma 30 s', 'V10': 'Relative timing sigma 0.15 s',
    'V11': 'Relative timing sigma 0.6 s', 'V12': '125 Hz + tighter relative timing',
    'V13': '125 Hz + low clutter', 'V14': '125 Hz + high clutter',
    'V15': '300 Hz + tighter relative timing',
    'V16': '125 Hz + signal-favoring + tight timing',
}
# A bounded local sweep, not a new orbit/GLRT campaign. All cases receive the
# same maximum budgets and shared starts; stop polishing early only on KKT success.
BUDGET = dict(roof_s=3., search_s=6., search_starts=3, polish_s=15.,
              polish_passes=2, cross_s=15., cross_passes=2)


def validate_spec(spec, satellites):
    if set(spec) != set(BASE):
        raise ValueError('Unexpected score hyperparameters')
    if any(not np.isfinite(v) or v <= 0 for v in spec.values()):
        raise ValueError('All hyperparameters must be positive and finite')
    if satellites < 1 or spec['detection_budget']/satellites >= 1:
        raise ValueError('Per-satellite detection probability must be below one')


class Objective(CalibrationObjective):
    def __init__(self, data, center, arm, spec):
        satellites = np.arange(len(data.numbers))
        validate_spec(spec, len(satellites))
        super().__init__(data, data.initial, satellites, False, 60.)
        self.spec = dict(spec)
        self.likelihood.detection_probability = spec['detection_budget']/len(satellites)
        self.likelihood.clutter_rate = spec['clutter_rate']
        self.base = old.PenaltyTimingObjective(data, data.initial, satellites,
            self.likelihood, spec['sigma_hz'], common_sigma_s=spec['common_sigma_s'],
            relative_sigma_s=spec['relative_sigma_s'])
        self.center = center
        self.features = ((data.rf-center)/1e9)[:, None]
        self.likelihood.features = self.features
        self.base.minimum_shift_s = max(self.base.minimum_shift_s, -20.)
        self.base.maximum_shift_s = min(self.base.maximum_shift_s, 20.)
        self.base.deadline = float('inf')
        if arm == 'zero-c': self.bounds[-1] = (0., 0.)
        elif arm != 'fitted-c': raise ValueError('Unknown RF arm')

    def curvature(self, vector):
        """Use the configured sigma in ALL Fisher blocks, including RF terms."""
        v = np.asarray(vector[:self.size])
        base_h, visible = _fisher_system(self.base, v, self.base.last)
        # The reused helper hardcodes the original timing prior. Replace it.
        base_h[6, 6] -= .01
        ids = np.arange(7, self.size)
        base_h[ids, ids] -= 1.
        base_h += self.base.penalty_curvature(v)
        _, _, jac = self.base.predict(v, with_jacobian=True)
        weights = self.likelihood.last_result['row_association_probability']*visible/self.base.sigma_hz**2
        h = np.zeros((len(vector), len(vector)))
        h[:self.size, :self.size] = base_h
        for column in range(self.features.shape[1]):
            physical = jac.transpose_multiply((weights*self.features[:, column, None]).ravel())
            cross = self.base.vector_gradient(physical, v)
            h[:self.size, self.size+column] = cross
            h[self.size+column, :self.size] = cross
        h[self.size:, self.size:] = self.features.T@(weights.sum(axis=1)[:, None]*self.features)
        return h


@lru_cache(maxsize=1)
def dependencies():
    return dict(old.dependencies(), **{str(Path(__file__)): digest(Path(__file__))})


@lru_cache(maxsize=2)
def inputs(scan):
    data, saved, source = old.previous.load(scan)
    seeds, hashes = [], {}
    for arm in ARMS:
        for mode in old.MODES:
            p = old.OUT/'final'/f'{scan}-{arm}-{mode}.json'
            r = json.loads(p.read_text())
            assert r['input_sha256'] == saved['input_sha256']
            hashes[str(p)] = digest(p)
            seeds.append((f'old-{arm}-{mode}', r['best']))
    return data, saved, source, seeds, hashes


def objective(data, saved, arm, mode):
    return Objective(data, saved['input_metadata']['rf_center_hz'], arm, SPECS[mode])


def reprice(obj, seed, arm, stage):
    obj.base.deadline = float('inf')
    return old.previous.reprice(obj, seed, arm, stage)


def finish(obj, data, best):
    obj.base.deadline = float('inf')
    metrics = diagnostics(obj, data, best)
    probs = obj.likelihood.last_result['row_association_probability']
    metrics['mean_signal_posterior'] = float(probs.sum(axis=1).mean())
    metrics['mean_clutter_posterior'] = 1.-metrics['mean_signal_posterior']
    metrics['strong_soft_fraction'] = metrics['strong_soft_windows']/len(data.times)
    return metrics


def save(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Each job has an exclusive destination. Never overwrite historical results.
    with path.open('x') as stream:
        json.dump(record, stream, default=serial, indent=2, allow_nan=False)


def run(task):
    scan, arm, mode = task
    target = OUT/'initial'/f'{scan}-{arm}-{mode}.json'
    data, saved, source, shared_seeds, hashes = inputs(scan)
    if target.exists():
        r = json.loads(target.read_text())
        assert r['dependencies'] == dependencies() and r['input_sha256'] == saved['input_sha256']
        assert r['spec'] == SPECS[mode] and r['seed_sources'] == hashes
        return str(target)
    begun = time.monotonic()
    obj = objective(data, saved, arm, mode)
    records = [reprice(obj, seed, arm, name) for name, seed in shared_seeds]
    def fitted(stage, seed, budget, fixed=False):
        point = [0., 0.] if fixed else seed['point_km']
        r = fit(obj, feasible_start(obj, seed, 20., arm), point, budget, fixed, radius_km=4.)
        r['stage'] = stage
        records.append(r)
        return r
    roofs = [fitted(f'roof-{a}', saved['arms'][a]['roof'], BUDGET['roof_s'], True) for a in ARMS]
    roof = min(roofs, key=lambda r: r['objective'])
    ordered = sorted(records[:len(shared_seeds)], key=lambda r: r['objective'])
    second = next((r for r in ordered[1:] if np.linalg.norm(np.array(r['point_km'])-ordered[0]['point_km']) >= .1), ordered[1])
    for i, seed in enumerate([ordered[0], second, roof]):
        fitted(f'search-{i}', seed, BUDGET['search_s'])
    for i in range(BUDGET['polish_passes']):
        best = best_record(records)
        if finish(obj, data, best)['converged']: break
        fitted(f'polish-{i}', best, BUDGET['polish_s'])
    best = best_record(records)
    metrics = finish(obj, data, best)
    # Common reference score is a diagnostic only, never a selection criterion.
    reference = objective(data, saved, arm, 'C1')
    common = finish(reference, data, best)
    r = dict(scope=__doc__, scan=scan, arm=arm, mode=mode, spec=SPECS[mode],
        dependencies=dependencies(), seed_sources=hashes, source=str(source), source_sha256=digest(source),
        input_sha256=saved['input_sha256'], windows=len(data.times), numbers=data.numbers,
        fit_original_rows=data.original_rows, evaluation_original_rows=data.original_rows,
        heldout_original_rows=[], radius_km=4., common_bound_s=10., total_timing_bound_s=20.,
        maximum_budgets_s=BUDGET, best=best, roof=roof, records=records,
        timing=old.previous.timing_and_gradient(obj, best),
        common_reference_data_nll=common['data_nll'], common_reference_objective=common['objective'],
        elapsed_s=time.monotonic()-begun, **metrics)
    save(target, r)
    print('INITIAL', scan, arm, mode, round(r['distance_m']), 'm', 'KKT', round(r['kkt'], 5),
          'seconds', round(r['elapsed_s'], 1), flush=True)
    return str(target)


@lru_cache(maxsize=2)
def initial_pool(scan):
    paths = [OUT/'initial'/f'{scan}-{a}-{m}.json' for a in ARMS for m in SPECS]
    return [json.loads(p.read_text()) for p in paths], {str(p): digest(p) for p in paths}


def cross(task):
    scan, arm, mode = task
    target = OUT/'final'/f'{scan}-{arm}-{mode}.json'
    pool, hashes = initial_pool(scan)
    if target.exists():
        r = json.loads(target.read_text())
        assert r['dependencies'] == dependencies() and r['cross_sources'] == hashes
        return str(target)
    begun = time.monotonic()
    data, saved, _, _, _ = inputs(scan)
    obj = objective(data, saved, arm, mode)
    # Fresh JSON copy: cached initial results must not change between jobs.
    original = next(r for r in pool if (r['arm'], r['mode']) == (arm, mode))
    r = json.loads(json.dumps(original))
    seeds = [reprice(obj, z['best'], arm, f'cross-{z["arm"]}-{z["mode"]}') for z in pool]
    r['cross_seed_gain_nll'] = r['objective']-min(s['objective'] for s in seeds)
    r['records'].extend(seeds)
    for i in range(BUDGET['cross_passes']):
        best = best_record(r['records'])
        if finish(obj, data, best)['converged']: break
        new = fit(obj, np.asarray(best['vector']), best['point_km'], BUDGET['cross_s'], False, radius_km=4.)
        new['stage'] = f'cross-polish-{i}'
        r['records'].append(new)
    best = best_record(r['records'])
    metrics = finish(obj, data, best)
    common = finish(objective(data, saved, arm, 'C1'), data, best)
    r.update(best=best, cross_sources=hashes, timing=old.previous.timing_and_gradient(obj, best),
        common_reference_data_nll=common['data_nll'], common_reference_objective=common['objective'],
        cross_elapsed_s=time.monotonic()-begun, **metrics)
    save(target, r)
    print('FINAL', scan, arm, mode, round(r['distance_m']), 'm', 'KKT', round(r['kkt'], 5), flush=True)
    return str(target)


def self_check():
    """Numerical oracle/gradient checks before starting the sweep."""
    data, saved, _, shared, _ = inputs('N01')
    seed = shared[0][1]
    for arm in ARMS:
        for control, prior in [('C0', 'baseline'), ('C1', 'relative-only')]:
            new = objective(data, saved, arm, control)
            ref = old.make_objective(data, saved, arm, prior)
            v = feasible_start(new, seed, 20., arm)
            j, g = new.evaluate(v); j0, g0 = ref.evaluate(v)
            np.testing.assert_allclose(j, j0, atol=1e-8, rtol=0)
            np.testing.assert_allclose(g, g0, atol=1e-9, rtol=0)
            np.testing.assert_allclose(new.curvature(v), ref.curvature(v), atol=1e-8, rtol=1e-10)
    errors = []
    for mode in SPECS:
        obj = objective(data, saved, 'fitted-c', mode)
        v = feasible_start(obj, seed, 20., 'fitted-c')
        value, grad = obj.evaluate(v)
        for index, step in [(2, .02), (3, .0001), (6, 1e-5), (7, 1e-5), (len(v)-1, .02)]:
            e = np.eye(len(v))[index]*step
            fd = (obj.evaluate(v+e)[0]-obj.evaluate(v-e)[0])/(2*step)
            np.testing.assert_allclose(fd, grad[index], atol=3e-4, rtol=3e-4)
            errors.append(abs(fd-grad[index]))
        obj.evaluate(v)
        h = obj.curvature(v)
        np.testing.assert_allclose(h, h.T, atol=1e-8, rtol=0)
        assert np.linalg.eigvalsh(h).min() > -1e-6
        assert obj.likelihood.last_result['sigma_hz'] == SPECS[mode]['sigma_hz']
        assert obj.likelihood.last_result['clutter_rate'] == SPECS[mode]['clutter_rate']
        assert np.isfinite(value)
    print('CHECK PASSED', len(errors), 'gradient checks; largest absolute error', max(errors), flush=True)


def summarize(rows):
    lookup = {(r['scan'], r['arm'], r['mode']): r for r in rows}
    summary = []
    for arm in ARMS:
        for mode in SPECS:
            subset = [r for r in rows if r['arm'] == arm and r['mode'] == mode]
            if not subset: continue
            errors = np.array([r['distance_m'] for r in subset])
            delta = errors-np.array([lookup[r['scan'], arm, 'C1']['distance_m'] for r in subset])
            summary.append(dict(arm=arm, mode=mode, label=LABELS[mode], scans=len(subset),
                median_error_m=float(np.median(errors)), mean_error_m=float(np.mean(errors)),
                p90_error_m=float(np.quantile(errors, .9)), maximum_error_m=float(max(errors)),
                below_500m=int(sum(errors < 500)), below_1km=int(sum(errors < 1000)),
                converged=sum(r['converged'] for r in subset), boundary=sum(r['boundary'] for r in subset),
                converged_below_1km=sum(r['converged'] and r['distance_m'] < 1000 for r in subset),
                improved_vs_C1=int(sum(delta < -1)), worsened_vs_C1=int(sum(delta > 1)),
                median_change_vs_C1_m=float(np.median(delta)),
                median_owner_rms_hz=float(np.median([r['owner_rms_hz'] for r in subset])),
                median_posterior_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in subset])),
                mean_signal_posterior=float(np.mean([r['mean_signal_posterior'] for r in subset])),
                common_reference_data_nll=float(sum(r['common_reference_data_nll'] for r in subset))))
    return summary


def audit(stage='final'):
    rows = []
    for scan in SCANS:
        data, saved, source, _, _ = inputs(scan)
        for arm in ARMS:
            for mode in SPECS:
                path = OUT/stage/f'{scan}-{arm}-{mode}.json'
                r = json.loads(path.read_text())
                assert r['dependencies'] == dependencies() and r['spec'] == SPECS[mode]
                assert r['input_sha256'] == saved['input_sha256'] and r['source_sha256'] == digest(source)
                assert r['fit_original_rows'] == r['evaluation_original_rows'] == data.original_rows.tolist()
                assert r['numbers'] == data.numbers.tolist() and not r['heldout_original_rows']
                assert r['maximum_budgets_s'] == BUDGET
                if stage == 'final':
                    assert r['cross_sources'] == initial_pool(scan)[1]
                obj = objective(data, saved, arm, mode)
                checked = finish(obj, data, r['best'])
                for k, v in checked.items():
                    np.testing.assert_allclose(v, r[k], atol=1e-7, rtol=0)
                assert r['objective'] <= min(z['objective'] for z in r['records'])+1e-7
                assert np.linalg.norm(r['best']['point_km']) <= 4.+1e-7
                assert abs(r['best']['vector'][6]) <= 10.+1e-7
                assert max(abs(np.array(r['best']['parameters'])[6:])) <= 20.+1e-7
                if arm == 'zero-c': assert r['best']['coefficient'] == 0.
                common = finish(objective(data, saved, arm, 'C1'), data, r['best'])
                np.testing.assert_allclose(common['data_nll'], r['common_reference_data_nll'], atol=1e-7, rtol=0)
                rows.append(r)
    return rows


def csv_write(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def report(stage):
    rows = audit(stage)
    totals = summarize(rows)
    target = OUT/stage
    csv_write(target/'summary.csv', totals)
    csv_write(target/'variants.csv', [dict(mode=m, label=LABELS[m], **s) for m, s in SPECS.items()])
    columns = ['scan', 'arm', 'mode', 'distance_m', 'converged', 'boundary', 'kkt', 'windows',
               'objective', 'data_nll', 'timing_prior_nll', 'owner_rms_hz',
               'posterior_weighted_residual_rms_hz', 'strong_soft_fraction', 'mean_signal_posterior',
               'common_reference_data_nll', 'common_reference_objective']
    per_scan = [{k:r[k] for k in columns} for r in rows]
    csv_write(target/'per-scan.csv', per_scan)
    result = dict(scope=__doc__, status='passed', cases=len(rows), specs=SPECS,
                  budgets=BUDGET, summary=totals, rows=per_scan, dependencies=dependencies())
    # These aggregate views are reproducible and replaceable; individual fits aren't.
    (target/'audit.json').write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
    render(target, rows, totals)
    print(json.dumps(totals, indent=2), flush=True)


def render(target, rows, totals):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    lookup = {(r['scan'],r['arm'],r['mode']):r for r in rows}
    order = ['C0', 'C1']+sorted([m for m in SPECS if m.startswith('V')],
        key=lambda m:next(r['median_error_m'] for r in totals if (r['arm'],r['mode'])==('fitted-c',m)))
    fig, axes = plt.subplots(1,2,figsize=(19,11),sharey=True)
    for ax,arm in zip(axes,ARMS):
        matrix=np.array([[lookup[s,arm,m]['distance_m'] for s in SCANS] for m in order])
        im=ax.imshow(matrix,aspect='auto',cmap='viridis_r',vmin=0,vmax=4000)
        for j,m in enumerate(order):
            for i,s in enumerate(SCANS):
                r=lookup[s,arm,m]
                text=f'{r["distance_m"]/1000:.2f}'
                text += '△' if r['boundary'] else ''
                text += '×' if not r['converged'] else ''
                ax.text(i,j,text,ha='center',va='center',fontsize=7,
                        color='white' if matrix[j,i]>1900 else 'black')
        ax.set_xticks(range(16),SCANS,rotation=55,ha='right')
        ax.set_yticks(range(len(order)),[f'{m}  {LABELS[m]}' for m in order],fontsize=9)
        ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0')
        ax.axhline(1.5,color='white',lw=2)
    fig.suptitle('Final position-score hyperparameters · N01–N16 independent 4 km searches',fontsize=17)
    fig.text(.5,.025,'Numbers = position error (km). △ = 4 km boundary; × = unconverged. Same observations, orbit bank, RX baseline and maximum budgets.\n16 new variants + 2 rerun controls. Development/in-sample comparison; no global-minimum guarantee.',ha='center',fontsize=10)
    fig.subplots_adjust(left=.22,right=.93,bottom=.13,top=.93,wspace=.08)
    cax=fig.add_axes([.95,.18,.012,.65]); fig.colorbar(im,cax=cax,label='Position error (m)')
    fig.savefig(target/'position-error-heatmap.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(17,10),sharey=True)
    colors={'fitted-c':'#0072B2','zero-c':'#D55E00'}
    for ax,metric,title in zip(axes,['median_error_m','p90_error_m'],['Median position error','90th-percentile position error']):
        for arm,offset in zip(ARMS,[-.17,.17]):
            vals=[next(r for r in totals if (r['arm'],r['mode'])==(arm,m)) for m in order]
            ax.barh(np.arange(len(order))+offset,[r[metric] for r in vals],height=.32,color=colors[arm],label='Fitted c' if arm=='fitted-c' else 'c = 0')
        ax.set_yticks(range(len(order)),[f'{m}  {LABELS[m]}' for m in order],fontsize=9)
        ax.set_title(title);ax.set_xlabel('Error (m)');ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    axes[0].invert_yaxis();axes[0].legend()
    fig.suptitle('16 final-score variants · same 16 scans in both RF arms',fontsize=16)
    fig.tight_layout(rect=(0,.04,1,.96))
    fig.text(.5,.015,'Best-found bounded local results; convergence and boundary details in heatmap/CSV. Variants ordered by fitted-c median, not cherry-picked per scan.',ha='center',fontsize=9)
    fig.savefig(target/'position-error-summary.png',dpi=150);plt.close(fig)
    winner=min((r for r in totals if r['arm']=='fitted-c' and r['mode'].startswith('V')),key=lambda r:r['median_error_m'])['mode']
    fig,axes=plt.subplots(2,1,figsize=(15,8),sharex=True,sharey=True)
    for ax,arm in zip(axes,ARMS):
        for mode,color,offset in [('C0','#999999',-.22),('C1','#0072B2',0),(winner,'#D55E00',.22)]:
            for i,scan in enumerate(SCANS):
                r=lookup[scan,arm,mode]
                ax.scatter(i+offset,r['distance_m'],color=color,marker='^' if r['boundary'] else 'o',s=45,label=f'{mode}: {LABELS[mode]}' if i==0 else None)
                if not r['converged']:ax.scatter(i+offset,r['distance_m'],marker='x',color='black',s=60)
        ax.axhline(1000,color='.6',ls='--');ax.axhline(4000,color='.6',ls=':')
        ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0');ax.set_ylabel('Position error (m)');ax.grid(alpha=.15)
    axes[0].legend(ncol=3,fontsize=9);axes[1].set_xticks(range(16),SCANS)
    fig.suptitle(f'Best new fitted-c cohort-median variant: {winner} · per-scan comparison',fontsize=15)
    fig.tight_layout(rect=(0,.035,1,.95))
    fig.text(.5,.01,'Same single variant across all scans and both arms. Triangle = boundary; × = unconverged. This cohort was used for tuning.',ha='center',fontsize=9)
    fig.savefig(target/'best-variant-per-scan.png',dpi=150);plt.close(fig)
    def table(records,keys):
        return '<table><tr>'+''.join(f'<th>{html.escape(k)}</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join(f'<td>{html.escape(str(round(r[k],3) if isinstance(r[k],float) else r[k]))}</td>' for k in keys)+'</tr>' for r in records)+'</table>'
    body='<h1>Final position-score hyperparameter sweep</h1><p>'+html.escape(__doc__)+'</p>'
    body+='<p>512 new-variant fits + 64 matched control fits. Score parameters were fixed before fitting. All fits use full associated-window inputs; no held-out rows. Detection budget is an expected-count budget, so 1.6 is allowed when its per-satellite probability remains below one.</p>'
    body+='<h2>Frozen settings</h2>'+table([dict(mode=m,**v) for m,v in SPECS.items()],['mode',*BASE])
    body+='<h2>Position accuracy</h2><img src="position-error-summary.png"><img src="position-error-heatmap.png"><img src="best-variant-per-scan.png">'
    body+=table(totals,['arm','mode','median_error_m','mean_error_m','p90_error_m','below_1km','converged','boundary','improved_vs_C1','worsened_vs_C1'])
    body+='<h2>Frequency fit, separately from position</h2><p>Posterior RMS changes its effective weights with the model. Owner RMS retains original owners and rows. Raw NLL is not comparable across different sigma/detection/clutter assumptions. Common-reference NLL evaluates each returned parameter vector under C1 without refitting; it is a diagnostic, not a selection criterion.</p>'
    body+=table(totals,['arm','mode','median_owner_rms_hz','median_posterior_rms_hz','mean_signal_posterior','common_reference_data_nll'])
    body+='<p><a href="summary.csv">Summary CSV</a> · <a href="per-scan.csv">All per-scan results</a> · <a href="audit.json">Reconstruction audit</a></p>'
    (target/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Position score sweep</title><style>body{font:16px system-ui;max-width:1500px;margin:35px auto;padding:15px}table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #ddd;padding:6px;text-align:right}img{width:100%}p{line-height:1.5}</style>'+body)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['check','initial','cross','report'])
    parser.add_argument('--scans',nargs='+',choices=SCANS,default=SCANS)
    parser.add_argument('--modes',nargs='+',choices=list(SPECS),default=list(SPECS))
    parser.add_argument('--workers',type=int,default=12)
    parser.add_argument('--report-stage',choices=['initial','final'],default='final')
    args=parser.parse_args()
    if args.stage=='check':self_check();return
    if args.stage=='report':report(args.report_stage);return
    OUT.mkdir(exist_ok=True)
    manifest=dict(scope=__doc__,specs=SPECS,budgets=BUDGET,scans=SCANS,arms=ARMS,dependencies=dependencies())
    path=OUT/'protocol.json'
    if path.exists():assert json.loads(path.read_text())==json.loads(json.dumps(manifest))
    else:save(path,manifest)
    jobs=[(s,a,m) for s in args.scans for m in args.modes for a in ARMS]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run if args.stage=='initial' else cross,j) for j in jobs]):
            future.result()


if __name__=='__main__':main()
