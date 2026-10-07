"""Matched, bounded N01--N16 GLRT-mark position and soft-association prototypes.

Frozen known-roof calibration, selected satellite bank and all top-one associated
windows. Refit position/timing/RX/RF parameters; soft association can change within
the frozen bank. This does not rerun discrete catalogue selection or raw IQ.
"""
import argparse
import csv
import hashlib
import inspect
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent/'2026_10_04_t1_at_v1_replication'
sys.path.insert(0, str(PREVIOUS))
import run as replication
from numeric_data import enable_research_model
enable_research_model()
import position_score_sweep as sweep
from convergence_fisher import fit
from resume_position_convergence import best_record
from timing_bound_comparison import feasible_start, digest
from subset_positions import serial
from soft_solvers import _normal_matrix, _parameter_map
from marks import SingletonMarkedLikelihood, lane_marks, mark_settings

SCANS = tuple(f'N{i:02d}' for i in range(1, 17))
MODELS = {'T1AT': 'C0', 'V16': 'V16'}
MODES = ('control', 'signal-prior', 'precision', 'joint', 'shuffled-joint')
ARMS = ('fitted-c', 'zero-c')
BUDGET = dict(search_starts=2, search_s=1., polish_s=1., radius_km=4.)


class Objective(sweep.Objective):
    def __init__(self, data, saved, arm, model, mode):
        spec = sweep.SPECS[MODELS[model]]
        super().__init__(data, saved['input_metadata']['rf_center_hz'], arm, spec)
        marks = lane_marks(data.margin, data.receiver, data.channel,
                           shuffle=mode == 'shuffled-joint')
        odds, sigma = mark_settings(marks, mode)
        self.likelihood = SingletonMarkedLikelihood(data.measured, data.group, self.features,
            spec['detection_budget']/len(data.numbers), spec['clutter_rate'],
            self.likelihood.alias_hz, odds, sigma)
        self.base.likelihood = self.likelihood

    def curvature(self, vector):
        _, visible, jac = self.base.predict(vector[:self.size], with_jacobian=True)
        weights = self.likelihood.last_result['prediction_precision']*visible
        mapping = _parameter_map(self.base)
        h = np.zeros((len(vector), len(vector)))
        h[:self.size, :self.size] = mapping.T@_normal_matrix(jac, weights)@mapping
        h[:self.size, :self.size] += self.base.penalty_curvature(vector[:self.size])
        for i in range(self.features.shape[1]):
            physical = jac.transpose_multiply((weights*self.features[:, i, None]).ravel())
            cross = self.base.vector_gradient(physical, vector[:self.size])
            h[:self.size, self.size+i] = cross
            h[self.size+i, :self.size] = cross
        h[self.size:, self.size:] = self.features.T@(weights.sum(axis=1)[:, None]*self.features)
        return h


def metrics(obj, data, best):
    result = sweep.finish(obj, data, best)
    p = obj.likelihood.last_result['row_association_probability'].copy()
    winners = p.argmax(axis=1)
    result['soft_winner_numbers'] = np.where(p.max(axis=1) > .5, data.numbers[winners], -1)
    result['signal_probabilities'] = p.sum(axis=1)
    return result


def run_scan(task):
    scan, output = task
    data, saved, source, pool, seed_hashes = sweep.inputs(scan)
    # Same archived pool for all methods/arms, selected solely by trial objective.
    source_npz = source.with_suffix('.npz')
    output = Path(output)/scan
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for model in MODELS:
        for arm in ARMS:
            common = sweep.objective(data, saved, arm, MODELS[model])
            for mode in MODES:
                begun = time.monotonic()
                obj = Objective(data, saved, arm, model, mode)
                starts = [sweep.reprice(obj, seed, arm, label) for label, seed in pool]
                starts.sort(key=lambda r: r['objective'])
                first = starts[0]
                second = next((r for r in starts[1:] if np.linalg.norm(
                    np.asarray(r['point_km'])-first['point_km']) >= .1), starts[1])
                records = list(starts)
                for i, start in enumerate((first, second)):
                    record = fit(obj, feasible_start(obj, start, 20., arm), start['point_km'],
                                 BUDGET['search_s'], radius_km=4.)
                    record['stage'] = f'search-{i}'
                    records.append(record)
                best = best_record(records)
                polished = fit(obj, feasible_start(obj, best, 20., arm), best['point_km'],
                               BUDGET['polish_s'], radius_km=4.)
                polished['stage'] = 'polish'
                records.append(polished)
                best = best_record(records)
                values = metrics(obj, data, best)
                assert abs(values['objective']-best['objective']) < 1e-7
                assert np.linalg.norm(best['point_km']) <= 4.+1e-7
                if arm == 'zero-c':
                    assert best['coefficient'] == 0.
                reference = sweep.finish(common, data, best)
                result = dict(scan=scan, model=model, arm=arm, mode=mode,
                    scope=__doc__, spec=sweep.SPECS[MODELS[model]], budgets=BUDGET,
                    source=str(source_npz), input_sha256=digest(source_npz),
                    input_receipt_sha256=digest(source), seed_pool_sha256=seed_hashes,
                    original_rows=data.original_rows, numbers=data.numbers, windows=len(data.times),
                    implementation_sha256={str(p): digest(p) for p in (Path(__file__), HERE/'marks.py')},
                    best=best, records=records, common_reference_data_nll=reference['data_nll'],
                    elapsed_s=time.monotonic()-begun, **values)
                path = output/f'{model}-{arm}-{mode}.json'
                path.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
                rows.append(result)
            print(scan, model, arm, 'five variants complete', flush=True)
    return len(rows)


def summarize(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = [json.loads(p.read_text()) for p in sorted(Path(output).glob('N*/*.json'))]
    if len(rows) != 320:
        raise ValueError(f'Expected 320 fits, found {len(rows)}')
    lookup = {(r['scan'], r['model'], r['arm'], r['mode']): r for r in rows}
    pairs = []
    for r in rows:
        base = lookup[r['scan'], r['model'], r['arm'], 'control']
        assert all(r[k] == base[k] for k in ('input_sha256','original_rows','numbers','budgets','seed_pool_sha256'))
        other_arm = lookup[r['scan'], r['model'], 'zero-c' if r['arm']=='fitted-c' else 'fitted-c', r['mode']]
        assert all(r[k] == other_arm[k] for k in ('input_sha256','original_rows','numbers','budgets','seed_pool_sha256'))
        winner_changed = np.asarray(r['soft_winner_numbers']) != base['soft_winner_numbers']
        pairs.append(dict(scan=r['scan'], model=r['model'], arm=r['arm'], mode=r['mode'],
            windows=r['windows'], distance_m=r['distance_m'], error_change_m=r['distance_m']-base['distance_m'],
            rms_hz=r['posterior_weighted_residual_rms_hz'], rms_change_hz=r['posterior_weighted_residual_rms_hz']-base['posterior_weighted_residual_rms_hz'],
            common_nll_change=r['common_reference_data_nll']-base['common_reference_data_nll'],
            owner_rms_hz=r['owner_rms_hz'], converged=r['converged'], boundary=r['boundary'],
            kkt=r['kkt'], changed_soft_winners=int(winner_changed.sum()),
            mean_signal_posterior=r['mean_signal_posterior'], elapsed_s=r['elapsed_s']))
    with (HERE/'per_scan.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pairs[0])); writer.writeheader();writer.writerows(pairs)
    aggregate = []
    for model in MODELS:
        for arm in ARMS:
            for mode in MODES:
                selected = [r for r in pairs if (r['model'],r['arm'],r['mode'])==(model,arm,mode)]
                aggregate.append(dict(model=model,arm=arm,mode=mode,scans=len(selected),
                    median_error_m=float(np.median([r['distance_m'] for r in selected])),
                    median_error_change_m=float(np.median([r['error_change_m'] for r in selected])),
                    median_rms_change_hz=float(np.median([r['rms_change_hz'] for r in selected])),
                    improved=sum(r['error_change_m'] < -1 for r in selected),
                    worsened=sum(r['error_change_m'] > 1 for r in selected),
                    converged=sum(r['converged'] for r in selected),
                    changed_soft_winners=sum(r['changed_soft_winners'] for r in selected)))
    (HERE/'summary.json').write_text(json.dumps(aggregate,indent=2))
    figures = HERE/'figures';figures.mkdir(exist_ok=True)
    colors = dict(zip(MODES[1:], ('#0072B2','#009E73','#D55E00','#999999')))
    fig,axes=plt.subplots(2,2,figsize=(13,8),sharex=True)
    for i,model in enumerate(MODELS):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j]
            for mode in MODES[1:]:
                p=[lookup[s,model,arm,mode]['distance_m']-lookup[s,model,arm,'control']['distance_m'] for s in SCANS]
                ax.plot(range(1,17),p,'o-',color=colors[mode],label=mode,ms=3,lw=1)
            ax.axhline(0,color='black',lw=.8);ax.set(title=f'{model} · {arm}',ylabel='Position error change (m)',xticks=range(1,17))
    axes[0,0].legend(fontsize=8);axes[1,0].set_xlabel('Scan N');axes[1,1].set_xlabel('Scan N')
    fig.suptitle('GLRT marks: paired position changes against matched control\nNegative is better · bounded local development fits')
    fig.tight_layout();fig.savefig(figures/'position_changes.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for i,model in enumerate(MODELS):
        for mode in MODES[1:]:
            p=[r for r in pairs if r['model']==model and r['mode']==mode]
            axes[i].scatter([r['rms_change_hz'] for r in p],[r['error_change_m'] for r in p],label=mode,color=colors[mode],s=20,alpha=.7)
        axes[i].axhline(0,color='black',lw=.8);axes[i].axvline(0,color='black',lw=.8)
        axes[i].set(title=model,xlabel='Posterior-weighted RMS change (Hz)',ylabel='Position error change (m)')
    axes[0].legend(fontsize=8);fig.suptitle('Frequency fit and position accuracy are separate outcomes\nRMS weights change with the model; this is an in-sample diagnostic')
    fig.tight_layout();fig.savefig(figures/'fit_vs_position.png',dpi=160);plt.close(fig)
    # Snapshot read-only inputs and numerical dependencies for later reproduction.
    sources={}
    for r in rows:
        sources[r['source']]=r['input_sha256'];sources.update(r['seed_pool_sha256'])
    sources.update(sweep.dependencies())
    sources.update({str(HERE/p):digest(HERE/p) for p in ('marks.py','experiment.py')})
    (HERE/'provenance.json').write_text(json.dumps(dict(results_root=str(output),source_sha256=sources,
        result_sha256={str(p):digest(p) for p in sorted(Path(output).glob('N*/*.json'))}),indent=2))
    return aggregate


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=4);parser.add_argument('--summarize-only',action='store_true')
    args=parser.parse_args()
    if not args.summarize_only:
        args.output.mkdir(parents=True,exist_ok=False)
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(run_scan,(s,str(args.output))) for s in SCANS]):
                future.result()
    print(json.dumps(summarize(args.output),indent=2))
