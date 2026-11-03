"""Independent A/B ambiguity experiments on frozen top-one T1-AT v1 windows.

Two-pass development diagnostic, not blind localization: responsibility masks
and identities come from the saved fitted-c position result, NOT a new roof fit.
All retained windows train the fit; no folds or held-out rows. Same frozen mask,
bank, timing priors, starts and maximum search budget in fitted-c and c=0 arms.
Saved upstream receiver calibration stays fixed. No new RF, refinement, orbit
discovery or association selection. No satellite hypothesis is added/deleted.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for name in ('2026_10_04_ds13_18_scan_benchmark', '2026_10_04_t1_at_v1_replication',
             '2026_10_02_localization_benchmark', '2026_10_02_multiscan_localization',
             '2026_10_02_ds13_timing_em', '2026_10_05_ab_responsibilities'):
    sys.path.insert(0, str(REPO/'reports'/name))
from plot_responsibilities import load_case, SOURCE
from rf_calibration_diagnostic import CalibrationObjective
from timing_model import GLOBAL_SHIFT_SIGMA_S, INDIVIDUAL_SHIFT_SIGMA_S
from soft_solvers import _parameter_map, _normal_matrix
from convergence_fisher import fit
from position_direct import coordinate, coordinate_jacobian
from likelihood import Likelihood, freeze, ALIAS

ARMS = ('fitted-c', 'zero-c')
MODES = dict(baseline='Soft baseline', signal_only='Clutter-only filter',
             drop_only='Drop ambiguous\n+ soft', hard_only='Hard only',
             drop_hard='Drop ambiguous\n+ hard', penalty_1='Ambiguity\npenalty η=1',
             penalty_2='Ambiguity\npenalty η=2')
BUDGET = dict(start_s=5., starts=3, polish_s=10., roof_s=6., cross_s=6.)
RADIUS = 2.


def digest(path):
    return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False,
                   default=lambda v: v.tolist() if isinstance(v, np.ndarray) else v.item()))


def inputs(scan):
    meta = json.loads((SOURCE/scan/'input.json').read_text())
    saved = json.loads((SOURCE/scan/'all-100.json').read_text())
    with np.load(SOURCE/scan/'input.npz', allow_pickle=False) as z:
        data = SimpleNamespace(**{k: z[k].copy() for k in z.files})
    if digest(SOURCE/scan/'input.npz') != meta['input_sha256']:
        raise ValueError('Input hash mismatch')
    receipt = json.loads((HERE/'inputs'/f'{scan}.json').read_text())
    if receipt['saved_fit_sha256'] != digest(SOURCE/scan/'all-100.json'):
        raise ValueError('Saved fit changed')
    with np.load(HERE/'inputs'/f'{scan}.npz', allow_pickle=False) as z:
        frozen = {k: z[k].copy() for k in z.files}
    if digest(HERE/'inputs'/f'{scan}.npz') != receipt['mask_sha256']:
        raise ValueError('Frozen mask changed')
    return data, meta, saved, frozen, receipt


class Objective(CalibrationObjective):
    def __init__(self, data, center, frozen, arm, mode):
        super().__init__(data, data.initial, np.arange(len(data.numbers)), False, 120.)
        self.center = center
        self.features = ((data.rf-center)/1e9)[:, None]
        keep = np.ones(len(data.times), bool)
        if mode in ('signal_only', 'hard_only'):
            keep = frozen['real']
        if mode in ('drop_only', 'drop_hard'):
            keep = frozen['keep']
        hard = mode in ('hard_only', 'drop_hard')
        eta = float(mode[-1]) if mode.startswith('penalty_') else 0.
        self.likelihood = Likelihood(data.measured, self.features, len(data.numbers),
                                     keep, frozen['winner'], hard, eta)
        self.base.likelihood = self.likelihood
        self.base.minimum_shift_s = max(self.base.minimum_shift_s, -20.)
        self.base.maximum_shift_s = min(self.base.maximum_shift_s, 20.)
        self.base.deadline = float('inf')
        if arm == 'zero-c':
            self.bounds[-1] = (0., 0.)

    def curvature(self, vector):
        _, _, jac = self.base.predict(vector[:self.size], with_jacobian=True)
        w = self.likelihood.last_result['irls_weights']
        mapping = _parameter_map(self.base)
        h = np.zeros((len(vector), len(vector)))
        h[:self.size, :self.size] = mapping.T @ _normal_matrix(jac, w) @ mapping
        if self.base.common_prior:
            h[6, 6] += 1./GLOBAL_SHIFT_SIGMA_S**2
        h[7:self.size, 7:self.size] += np.eye(self.size-7)/INDIVIDUAL_SHIFT_SIGMA_S**2
        physical = jac.transpose_multiply((w*self.features[:, 0, None]).ravel())
        cross = self.base.vector_gradient(physical, vector[:self.size])
        h[:self.size, self.size] = cross
        h[self.size, :self.size] = cross
        h[self.size, self.size] = float(self.features[:, 0] @ (w.sum(axis=1)*self.features[:, 0]))
        return h


def prepare():
    for scan in ('A', 'B'):
        data, p, clutter, stats = load_case(scan, 'fitted-c')
        frozen = freeze(p, clutter)
        path = HERE/'inputs'/f'{scan}.npz'
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            np.savez_compressed(path, **frozen, probability=p, clutter=clutter,
                                original_rows=data.original_rows, numbers=data.numbers)
        with np.load(path) as z:
            for key, value in frozen.items():
                np.testing.assert_array_equal(z[key], value)
        save(path.with_suffix('.json'), dict(scan=scan, scope=__doc__,
            mask_sha256=digest(path), input_sha256=stats['sources'][str(SOURCE/scan/'input.npz')],
            saved_fit_sha256=digest(SOURCE/scan/'all-100.json'), responsibility_sources=stats['sources'],
            original_windows=len(p), ambiguous_dropped=int(np.sum(~frozen['unambiguous'])),
            all_clutter_winners=int(np.sum(~frozen['real'])),
            additional_clutter_dropped=int(np.sum(frozen['unambiguous'] & ~frozen['real'])),
            final_retained=int(np.sum(frozen['keep'])), seed='saved fitted-c best position',
            policy='drop second satellite responsibility > .05; separately reject clutter >= top satellite'))
    save(HERE/'protocol.json', dict(scope=__doc__, modes=MODES, budget=BUDGET, radius_km=RADIUS,
        sigma_hz=200., common_timing_sigma_s=GLOBAL_SHIFT_SIGMA_S,
        relative_timing_sigma_s=INDIVIDUAL_SHIFT_SIGMA_S, timing_bound_s=20.,
        mask_reference='saved fitted-c best fit, shared by both RF arms',
        start_policy='same three archived seeds: fitted-c best, zero-c best, fitted-c roof; c forced to zero only in c=0 arm',
        objective_selection='lowest actual variant score, never lowest position error',
        caveats=['Hard loss is pure fixed-identity Gaussian, no clutter alternative.',
                 'Penalty is dynamic conditional-signal min-entropy, not independent physical evidence.',
                 'Original hard horizon retained; no cone prior. Existing priors unchanged.',
                 'Mask does not re-admit or discard windows when trial position changes.',
                 'Same bank remains even if a satellite has no retained hard-assigned windows.',
                 '2 km bounded local searches; boundary solutions are not unconstrained minima.']))


def choose(records):
    lowest = min(records, key=lambda r:r['objective'])
    tolerance = 64*np.finfo(float).eps*max(1., abs(lowest['objective']))
    candidates = [r for r in records if r['objective'] <= lowest['objective']+tolerance]
    return min(candidates, key=lambda r:r['kkt_residual'])


def run_fit(obj, seed, stage, seconds, fixed=False):
    point = [0., 0.] if fixed else seed['point_km']
    result = fit(obj, np.asarray(seed['vector']), point, seconds, fixed, radius_km=RADIUS)
    result['stage'] = stage
    return result


def metrics(obj, data, frozen, record, arm, center):
    v = np.asarray(record['vector'])
    obj.base.deadline = float('inf')
    score, _ = obj.evaluate(v)
    train = obj.likelihood.last_result
    common = Objective(data, center, frozen, arm, 'baseline')
    common_score, _ = common.evaluate(v)
    soft = common.likelihood.last_result
    p = soft['row_association_probability']
    prediction, visible = common.base.predict(v[:common.size])
    prediction += (common.features @ common.likelihood.coefficients)[:, None]
    residual = (data.measured-prediction[np.arange(len(p)), frozen['winner']]+ALIAS/2)%ALIAS-ALIAS/2
    mask = obj.likelihood.keep
    second = np.sort(p, axis=1)[:, -2]
    result = dict(position_error_m=1000*float(np.linalg.norm(record['point_km'])),
        retained_windows=int(mask.sum()), original_windows=len(p), satellites=len(data.numbers),
        hard_assigned_satellites=int(len(np.unique(frozen['winner'][mask]))),
        objective=score, common_full_score=common_score,
        common_full_data_nll=soft['unpenalized_soft_nll'],
        ambiguity_penalty=train['ambiguity_penalty'],
        timing_prior=obj.base.penalty(v[:obj.size])[0],
        retained_fixed_winner_rms_hz=float(np.sqrt(np.mean(residual[mask]**2))),
        full_fixed_winner_rms_hz=float(np.sqrt(np.mean(residual**2))),
        full_ambiguous_percent=float(100*np.mean(second > .05)),
        full_clutter_winner_percent=float(100*np.mean(soft['row_clutter_probability'] > p.max(axis=1))),
        mean_clutter_probability=float(np.mean(soft['row_clutter_probability'])),
        hard_invisible_windows=train['hard_invisible_windows'],
        frozen_owner_invisible_windows=int(np.sum(~visible[np.arange(len(p)), frozen['winner']] & mask)),
        converged=bool(record['success'] and not record['fixed_location']),
        kkt=record['kkt_residual'], boundary=bool(np.linalg.norm(record['point_km']) > RADIUS-.001),
        max_absolute_timing_s=float(np.max(abs(obj.base.state(v[:obj.size])['total_shifts_s']))))
    return result


def run(task):
    scan, arm, mode = task
    target = HERE/'results'/f'{scan}-{arm}-{mode}.json'
    data, meta, saved, frozen, receipt = inputs(scan)
    deps = {str(p):digest(p) for p in (Path(__file__), HERE/'likelihood.py', Path(inspect.getfile(fit)))}
    if target.exists():
        old = json.loads(target.read_text())
        if old['dependencies'] != deps or old['mask_sha256'] != receipt['mask_sha256']:
            raise ValueError('Stale result; do not overwrite')
        return str(target)
    obj = Objective(data, meta['rf_center_hz'], frozen, arm, mode)
    # Every variant must reproduce the old baseline before modifying its loss.
    baseline = Objective(data, meta['rf_center_hz'], frozen, arm, 'baseline')
    seed_old = saved['arms'][arm]['best']
    baseline_value = baseline.evaluate(np.array(seed_old['vector']))[0]
    np.testing.assert_allclose(baseline_value, seed_old['objective'], atol=1e-7, rtol=0)
    seeds = [saved['arms']['fitted-c']['best'], saved['arms']['zero-c']['best'],
             saved['arms']['fitted-c']['roof']]
    records = []
    for i, seed in enumerate(seeds):
        r = run_fit(obj, seed, f'start-{i}', BUDGET['start_s'])
        records.append(r)
    records.append(run_fit(obj, choose(records), 'polish', BUDGET['polish_s']))
    roof = run_fit(obj, choose(records), 'roof-profile', BUDGET['roof_s'], True)
    records.append(run_fit(obj, roof, 'roof-cross', BUDGET['cross_s']))
    best = choose(records)
    obj.base.deadline = float('inf')
    best_metrics = metrics(obj, data, frozen, best, arm, meta['rf_center_hz'])
    obj.evaluate(np.asarray(roof['vector']))
    roof_metrics = dict(converged=roof['success'], kkt=roof['kkt_residual'],
                        gradient_per_100m=(np.asarray(roof['position_gradient_per_km'])*.1).tolist(),
                        gradient_norm_per_100m=float(np.linalg.norm(roof['position_gradient_per_km'])*.1))
    result = dict(scan=scan, arm=arm, mode=mode, label=MODES[mode], dependencies=deps,
        input_sha256=meta['input_sha256'], mask_sha256=receipt['mask_sha256'],
        scope=__doc__, budget=BUDGET, radius_km=RADIUS,
        original_distance_m=1000*float(np.linalg.norm(seed_old['point_km'])),
        original_baseline_score=baseline_value, best=best, metrics=best_metrics,
        roof=roof, roof_metrics=roof_metrics, records=records,
        elapsed_s=sum(r['elapsed_s'] for r in records)+roof['elapsed_s'])
    save(target, result)
    print('DONE', scan, arm, mode, round(best_metrics['position_error_m']), 'm',
          'KKT', round(best_metrics['kkt'], 5), 'ambiguity', round(best_metrics['full_ambiguous_percent'], 2), flush=True)
    return str(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--scans', nargs='+', default=['A', 'B'])
    parser.add_argument('--modes', nargs='+', default=list(MODES))
    parser.add_argument('--arms', nargs='+', default=list(ARMS))
    args = parser.parse_args()
    prepare()
    jobs = [(s, a, m) for s in args.scans for m in args.modes for a in args.arms]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run, job) for job in jobs]):
            future.result()


if __name__ == '__main__':
    main()
