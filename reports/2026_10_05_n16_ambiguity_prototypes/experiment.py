"""N01--N16 ambiguity prototypes; independent, matched 4 km position searches.

Frozen full-data top-one assigned windows and original selected satellite bank.
Masks/identities come from the saved fitted-c position result for BOTH RF arms.
No new calibration, GLRT refinement, association search, folds or held-out rows.
Known-roof upstream calibration: development-cohort analysis, not blind testing.
"""
import argparse
import hashlib
import inspect
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent/'2026_10_05_cone_prior_localization'
REPLICATION = HERE.parent/'2026_10_04_t1_at_v1_replication'
sys.path[:0] = [str(REPLICATION), str(SOURCE)]
import full_data_calibration as calibration
from numeric_data import enable_research_model
enable_research_model()
sys.path.insert(0, str(calibration.LEGACY))
import greedy_pool_two_scans as historical
sys.path.insert(0, str(historical.OLD))
from cone_objective import Objective as ConeObjective
from convergence_fisher import fit
from polish_position_score_sweep import slsqp_fit
from position_direct import coordinate_jacobian
sys.path.insert(0, str(HERE))
from likelihood import Likelihood, freeze, ALIAS

SCANS = tuple(f'N{i:02}' for i in range(1, 17))
ARMS = ('fitted-c', 'zero-c')
MODES = dict(baseline='Soft baseline', signal_only='Clutter-only filter',
    drop_only='Drop ambiguous + soft', hard_only='Hard only',
    drop_hard='Drop ambiguous + hard', penalty_1='Ambiguity penalty η=1',
    penalty_2='Ambiguity penalty η=2')
RADIUS = 4.
BUDGET = dict(starts=3, start_s=4., polish_s=8., slsqp_s=12., continuation_s=12.)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, allow_nan=False,
        default=lambda x: x.tolist() if isinstance(x, np.ndarray) else x.item()))


def load(scan):
    folder = SOURCE/'inputs'/scan
    receipt = json.loads((folder/'receipt.json').read_text())
    assert digest(folder/'base.npz') == receipt['inputs']['base']['input_sha256']
    with np.load(folder/'base.npz', allow_pickle=False) as z:
        data = SimpleNamespace(**{k:z[k].copy() for k in z.files})
    records = {a:json.loads((SOURCE/'polished'/f'{scan}-{a}-control.json').read_text()) for a in ARMS}
    for r in records.values():
        assert r['input_sha256'] == digest(folder/'base.npz')
        np.testing.assert_array_equal(r['numbers'], data.numbers)
        np.testing.assert_array_equal(r['fit_original_rows'], data.original_rows)
    return data, receipt, records


class Objective(ConeObjective):
    def __init__(self, data, center, arm, frozen, mode):
        # Strength zero uses only the compact 0--1 degree horizon ramp.
        super().__init__(data, center, arm, 0., None, None, None)
        self.likelihood = Likelihood(data, self.features, frozen, mode)
        self.base.likelihood = self.likelihood


def prepare(scans):
    for scan in scans:
        data, receipt, records = load(scan)
        old = ConeObjective(data, receipt['rf_center_hz'], 'fitted-c', 0., None, None, None)
        value, _ = old.evaluate(np.asarray(records['fitted-c']['best']['vector']))
        np.testing.assert_allclose(value, records['fitted-c']['best']['objective'], atol=1e-7, rtol=0)
        p = old.likelihood.last_result['row_association_probability']
        clutter = old.likelihood.last_result['row_clutter_probability']
        frozen = freeze(p, clutter)
        path = HERE/'inputs'/f'{scan}.npz'
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            np.savez_compressed(path, **frozen, probability=p, clutter=clutter,
                                original_rows=data.original_rows, numbers=data.numbers)
        with np.load(path) as z:
            for k, v in frozen.items():
                np.testing.assert_array_equal(z[k], v)
        save(path.with_suffix('.json'), dict(scan=scan, original_windows=len(p),
            ambiguous_dropped=int(np.sum(~frozen['unambiguous'])),
            clutter_dropped=int(np.sum(~frozen['real'])), retained=int(frozen['keep'].sum()),
            extra_clutter_dropped=int(np.sum(frozen['unambiguous'] & ~frozen['real'])),
            mask_sha256=digest(path), input_sha256=digest(SOURCE/'inputs'/scan/'base.npz'),
            seeds={a:digest(SOURCE/'polished'/f'{scan}-{a}-control.json') for a in ARMS}))
    save(HERE/'protocol.json', dict(scope=__doc__, modes=MODES, radius_km=RADIUS,
        budget=BUDGET, sigma_hz=200., common_timing_sigma_s=10., relative_timing_sigma_s=1/3,
        detection_budget=.8, clutter_rate=2., horizon='quintic 0–1 degree; no cone weighting',
        common_timing_bound_s=10., total_satellite_timing_bound_s=20.,
        responsibility_threshold=.05, mask_reference='saved fitted-c best position',
        hard='fixed winner Gaussian; no clutter fallback; below-horizon owners infeasible',
        penalty='eta * sum(-log(max satellite probability conditional on signal))',
        seeds='same saved fitted-c best, c=0 best and fitted-c roof for every mode/arm',
        selection='lowest objective; near-exact ties choose lower KKT, never lower position error',
        convergence='scaled constrained KKT <= 0.001; boundary is not an unconstrained minimum'))


def inputs(scan):
    data, receipt, records = load(scan)
    meta = json.loads((HERE/'inputs'/f'{scan}.json').read_text())
    assert meta['input_sha256'] == digest(SOURCE/'inputs'/scan/'base.npz')
    for a in ARMS:
        assert meta['seeds'][a] == digest(SOURCE/'polished'/f'{scan}-{a}-control.json')
    assert meta['mask_sha256'] == digest(HERE/'inputs'/f'{scan}.npz')
    with np.load(HERE/'inputs'/f'{scan}.npz', allow_pickle=False) as z:
        frozen = {k:z[k].copy() for k in z.files}
    return data, receipt, records, frozen, meta


def choose(records):
    lowest = min(r['objective'] for r in records)
    tol = 64*np.finfo(float).eps*max(1., abs(lowest))
    return min((r for r in records if r['objective'] <= lowest+tol), key=lambda r:r['kkt_residual'])


def run_fit(obj, seed, stage, seconds):
    vector = np.array(seed['vector'])
    for i, (lo, hi) in enumerate(obj.bounds):
        if lo is not None: vector[i] = max(lo, vector[i])
        if hi is not None: vector[i] = min(hi, vector[i])
    result = fit(obj, vector, seed['point_km'], seconds, False, radius_km=RADIUS)
    result['stage'] = stage
    return result


def metrics(obj, data, frozen, best, arm, center):
    v = np.asarray(best['vector'])
    obj.base.deadline = float('inf')
    score, _ = obj.evaluate(v)
    train = obj.likelihood.last_result
    common = Objective(data, center, arm, frozen, 'baseline')
    common_score, _ = common.evaluate(v)
    soft = common.likelihood.last_result
    p = soft['row_association_probability']
    pred, visible = common.base.predict(v[:common.size])
    pred += (common.features@common.likelihood.coefficients)[:, None]
    residual = (data.measured-pred[np.arange(len(p)), frozen['winner']]+ALIAS/2)%ALIAS-ALIAS/2
    mask = obj.likelihood.keep
    penalty = Objective(data, center, arm, frozen, 'penalty_1')
    penalty.evaluate(v)
    return dict(position_error_m=1000*float(np.linalg.norm(best['point_km'])),
        retained_windows=int(mask.sum()), original_windows=len(p), satellites=len(data.numbers),
        objective=score, common_full_score=common_score,
        common_full_data_nll=soft['unpenalized_soft_nll'],
        ambiguity_penalty=train['ambiguity_penalty'],
        mean_conditional_min_entropy=penalty.likelihood.last_result['mean_conditional_min_entropy'],
        timing_prior=obj.base.penalty(v[:obj.size])[0],
        retained_fixed_winner_rms_hz=float(np.sqrt(np.mean(residual[mask]**2))),
        full_fixed_winner_rms_hz=float(np.sqrt(np.mean(residual**2))),
        full_ambiguous_percent=float(100*np.mean(np.sort(p, axis=1)[:, -2] > .05)),
        mean_clutter_probability=float(np.mean(soft['row_clutter_probability'])),
        hard_invisible_windows=train['hard_invisible_windows'],
        frozen_owner_invisible_windows=int(np.sum(~visible[np.arange(len(p)), frozen['winner']] & mask)),
        converged=bool(best['success']), kkt=best['kkt_residual'],
        boundary=bool(np.linalg.norm(best['point_km']) >= RADIUS-.001),
        max_absolute_timing_s=float(np.max(abs(obj.base.state(v[:obj.size])['total_shifts_s']))))


def run(task):
    started = time.monotonic()
    scan, arm, mode = task
    target = HERE/'results'/f'{scan}-{arm}-{mode}.json'
    deps = {str(p):digest(p) for p in (Path(__file__), HERE/'likelihood.py',
        Path(inspect.getfile(fit)), Path(inspect.getfile(ConeObjective)))}
    data, receipt, saved, frozen, meta = inputs(scan)
    if target.exists():
        prior = json.loads(target.read_text())
        assert prior['dependencies'] == deps and prior['input_receipt'] == meta
        return str(target)
    center = receipt['rf_center_hz']
    control = Objective(data, center, arm, frozen, 'baseline')
    old = saved[arm]['best']
    value, _ = control.evaluate(np.array(old['vector']))
    np.testing.assert_allclose(value, old['objective'], atol=1e-7, rtol=0)
    obj = Objective(data, center, arm, frozen, mode)
    seeds = [saved['fitted-c']['best'], saved['zero-c']['best'], saved['fitted-c']['roof']]
    records = [run_fit(obj, seed, f'shared-start-{i}', BUDGET['start_s']) for i, seed in enumerate(seeds)]
    records.append(run_fit(obj, choose(records), 'fisher-polish', BUDGET['polish_s']))
    if not choose(records)['success']:
        records.append(slsqp_fit(obj, choose(records), BUDGET['slsqp_s'], radius_km=RADIUS))
    if not choose(records)['success']:
        records.append(run_fit(obj, choose(records), 'fisher-continuation', BUDGET['continuation_s']))
    best = choose(records)
    stats = metrics(obj, data, frozen, best, arm, center)
    if stats['hard_invisible_windows']:
        raise ValueError('Accepted hard fit contains an infeasible owner')
    save(target, dict(scan=scan, arm=arm, mode=mode, label=MODES[mode],
        dependencies=deps, input_receipt=meta, original_distance_m=saved[arm]['distance_m'],
        best=best, metrics=stats, records=records, elapsed_s=time.monotonic()-started))
    print('DONE', scan, arm, mode, round(stats['position_error_m']), 'm',
        'KKT', round(stats['kkt'], 5), 'elapsed', round(time.monotonic()-started, 1), flush=True)
    return str(target)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scans', nargs='+', choices=SCANS, default=SCANS)
    p.add_argument('--modes', nargs='+', choices=MODES, default=list(MODES))
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--prepare-only', action='store_true')
    args = p.parse_args()
    prepare(args.scans)
    if not args.prepare_only:
        tasks = [(s, a, m) for s in args.scans for m in args.modes for a in ARMS]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for f in as_completed([pool.submit(run, t) for t in tasks]):
                f.result()
