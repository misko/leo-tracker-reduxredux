"""Independent 2 km position-profile searches on predeclared association subsets.

Ranking is fixed at the capture roof using fitted-c for both RF arms. The common
100% cohort contains only frozen assigned top-response windows. No new RF data,
greedy re-selection, or data-dependent ranking at trial positions.
"""
import argparse
import copy
import csv
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
BULK = Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
OUT = HERE / 'subset-position-search'
WORK = BULK / 'subset-position-search-20261004'
sys.path.insert(0, str(BULK))
from profile_top_2km import Engine, save
from replay import digest
from rf_calibration_diagnostic import CalibrationObjective

METHODS = ('rms', 'support', 'glrt')
FRACTIONS = (.25, .5, .75, 1.)


def select_subset(numbers, row_ids, owners, margins, rms, fraction, method):
    numbers = np.asarray(numbers); row_ids = np.asarray(row_ids)
    owners = np.asarray(owners); margins = np.asarray(margins)
    if method in ('rms', 'support'):
        if method == 'rms':
            ranked = sorted(numbers, key=lambda n: (rms[int(n)], int(n)))
        else:
            # The caller passes stable sorted numbers; the stored ranking uses count,
            # then span, then NORAD through support_rank below.
            ranked = sorted(numbers, key=lambda n: (-np.sum(owners == n), int(n)))
        selected = np.array(sorted(ranked[:math.ceil(len(numbers) * fraction)]))
        keep = np.isin(owners, selected)
    else:
        ranked = np.lexsort((row_ids, -margins))
        keep = np.zeros(len(row_ids), dtype=bool)
        keep[ranked[:math.ceil(len(row_ids) * fraction)]] = True
        selected = numbers.copy()  # Same complete candidate bank for window-quality arms.
    return selected, keep


def prepare():
    OUT.mkdir(exist_ok=True); WORK.mkdir(exist_ok=True)
    metrics = list(csv.DictReader((HERE / 'satellite-statistics/satellites.csv').open()))
    for scan in 'AB':
        z = np.load(BULK / f'position-top-2km/{scan}-profile-input.npz')
        d = np.load(HERE / f'{scan}-assigned-observations.npz')
        mapping = {int(r): i for i, r in enumerate(z['original_rows'])}
        ids = np.array([mapping[int(r)] for r in d['row_id']])
        refined_path = BULK / ('full-scan-A-refinement/refined.json' if scan == 'A' else 'position-top-2km/B-refinement/refined.json')
        refined = json.loads(refined_path.read_text())['records']
        margin = {int(r['row_index']): r['refinement'].get('margin', r['original_margin']) for r in refined}
        scores = np.array([margin[int(r)] for r in d['row_id']])
        rms = {int(r['satellite']): float(r['rms_hz']) for r in metrics if r['scan'] == scan and r['arm'] == 'fitted-c'}
        numbers = z['numbers']
        support_rank = sorted(numbers, key=lambda n: (-int(np.sum(d['satellite'] == n)),
            -float(np.ptp(d['time_s'][d['satellite'] == n])), int(n)))
        cases = []
        for method in METHODS:
            for fraction in FRACTIONS:
                selected, keep = select_subset(numbers, d['row_id'], d['satellite'], scores, rms, fraction, method)
                if method == 'support':
                    selected = np.array(sorted(support_rank[:math.ceil(len(numbers) * fraction)]))
                    keep = np.isin(d['satellite'], selected)
                case_id = 'all-100' if fraction == 1 else f'{method}-{int(fraction * 100)}'
                row = dict(scan=scan, method=method, fraction=fraction, case_id=case_id,
                    rows=ids[keep], original_rows=d['row_id'][keep], numbers=selected,
                    n_windows=int(keep.sum()), n_candidates=len(selected),
                    n_owners=len(np.unique(d['satellite'][keep])),
                    rx_counts=[int(np.sum(d['rx'][keep] == r)) for r in (0, 1)],
                    actual_window_fraction=float(keep.mean()),
                    refined_glrt_min=float(scores[keep].min()), refined_glrt_max=float(scores[keep].max()))
                cases.append(row)
        sources = [refined_path, HERE / f'{scan}-assigned-observations.npz',
                   HERE / 'satellite-statistics/satellites.csv', BULK / f'position-top-2km/{scan}-profile-input.npz']
        save(OUT / f'{scan}-subsets.json', dict(cases=cases, rms_rank=sorted(rms, key=lambda n: (rms[n], n)),
            support_rank=support_rank, sources={str(p): digest(p) for p in sources},
            scope='All fractions drawn from frozen fitted-c assigned windows only. Both RF arms use identical selection. Window ranking retains full candidate bank.'))


class SubsetEngine(Engine):
    def __init__(self, scan, arm, subset):
        super().__init__(scan, arm)
        evidence = json.loads((HERE / 'orientation-evidence.json').read_text())
        self.lat, self.lon = evidence['operator_roof_lat_lon']
        full = self.data
        rows = np.array(subset['rows'], int)
        columns = np.array([int(np.flatnonzero(full.numbers == n)[0]) for n in subset['numbers']])
        data = copy.copy(full)
        for name in ('times', 'measured', 'rf', 'receiver', 'channel', 'group', 'margin', 'original_rows',
                     'fixed_receiver_hz', 'raw_refined_hz'):
            setattr(data, name, getattr(full, name)[rows].copy())
        data.numbers = full.numbers[columns]
        data.position = full.position[columns]; data.velocity = full.velocity[columns]
        seed = json.loads((HERE / f'gradient-by-satellite/{scan}-{arm}.json').read_text())['roof_fit']
        data.initial = np.r_[seed['vector'][:6], np.asarray(seed['total_timing_s'])[columns]]
        self.data = data
        self.obj = CalibrationObjective(data, data.initial, np.arange(len(data.numbers)), False, 8.)
        # Preserve the same RF feature origin in every subset.
        self.obj.center = float(np.mean(np.unique(full.rf)))
        self.obj.features = ((data.rf - self.obj.center) / 1e9)[:, None]
        self.obj.likelihood.features = self.obj.features
        self.obj.base.minimum_shift_s = max(self.obj.base.minimum_shift_s, -20.)
        self.obj.base.maximum_shift_s = min(self.obj.base.maximum_shift_s, 20.)
        if arm == 'zero-c':
            self.obj.bounds[-1] = (0., 0.)
        self.initial = self.obj.initial.copy()
        self.initial[-1] = seed['c_hz_per_ghz'] if arm == 'fitted-c' else 0.
        self.cache = {}; self.calls = []
        self.folder = WORK / f'{scan}-{subset["case_id"]}-{arm}'
        self.folder.mkdir(exist_ok=True)
        for path in sorted(self.folder.glob('fit-*.json')):
            row = json.loads(path.read_text()); self.calls.append(row)
            key = tuple(np.round([row['east_m'], row['north_m']], 5))
            previous = self.cache.get(key)
            if previous is None or (row['success'] and not previous['success']) or (
                    row['success'] == previous['success'] and row['objective'] < previous['objective']):
                self.cache[key] = row


def design():
    rng = np.random.default_rng(20261004)
    points = [np.zeros(2)]
    for radius in (.7, 1.4, 2.):
        for sector in range(4):
            angle = rng.uniform(sector * np.pi / 2, (sector + 1) * np.pi / 2)
            points.append(radius * np.array([np.sin(angle), np.cos(angle)]))
    points += [2 * np.array([np.sin(j * np.pi / 4), np.cos(j * np.pi / 4)]) for j in range(8)]
    return points


def run_case(task):
    scan, arm, case_id = task
    target = OUT / f'{scan}-{case_id}-{arm}.json'
    if target.exists():
        return json.loads(target.read_text())
    subset = next(r for r in json.loads((OUT / f'{scan}-subsets.json').read_text())['cases'] if r['case_id'] == case_id)
    engine = SubsetEngine(scan, arm, subset)
    started = time.monotonic()

    def fitted(point, label='search', start=None):
        for attempt in range(3):
            result = engine.fit(point, label, force_start=start)
            if result['success']:
                return result
            start = result['vector']
        # A near-stationary Fisher/Newton step can stall at floating-point
        # precision. Use a bounded alternative optimizer, then re-check with
        # the original convergence criterion; never silently relax tolerance.
        scale = engine.obj.scale
        bounds = list(engine.obj.bounds)
        bounds[:2] = [(v, v) for v in engine.coordinate(point)]
        scaled_bounds = [(None if lo is None else lo/s, None if hi is None else hi/s)
                         for (lo, hi), s in zip(bounds, scale)]
        engine.obj.base.deadline = float('inf')
        def nuisance_objective(y):
            value, gradient = engine.obj.evaluate(y * scale)
            return value, gradient * scale
        alternate = minimize(nuisance_objective, np.array(start)/scale, jac=True, method='L-BFGS-B',
            bounds=scaled_bounds, options=dict(maxiter=500, maxfun=1500, ftol=1e-15, gtol=1e-5, maxls=40))
        result = engine.fit(point, label+'-lbfgsb-check', force_start=alternate.x*scale)
        if result['success']:
            return result
        # Final near-stationary check with the actual gradient Hessian instead
        # of the Fisher approximation. Bounds and convergence tolerance remain
        # unchanged; permit only roundoff-sized objective differences.
        from truth_start_diagnostic import projected_gradient
        current = np.array(result['vector'])
        for _ in range(5):
            value, gradient = engine.obj.evaluate(current)
            pg, free = projected_gradient(current, gradient, bounds, scale)
            norm = np.max(abs(pg)); indices = np.flatnonzero(free)
            if norm <= 1e-3:
                break
            hessian = np.zeros((len(indices), len(indices)))
            for j, index in enumerate(indices):
                step = np.zeros(len(current)); step[index] = scale[index]*1e-4
                gp = engine.obj.evaluate(current+step)[1]
                gm = engine.obj.evaluate(current-step)[1]
                hessian[:, j] = ((gp-gm)*scale/2e-4)[indices]
            hessian = (hessian+hessian.T)/2
            damping = max(0., 1e-8 - np.linalg.eigvalsh(hessian).min())
            direction = np.zeros(len(current))
            direction[indices] = np.linalg.solve(hessian+damping*np.eye(len(indices)), -pg[indices])*scale[indices]
            accepted = False
            for fraction in 2. ** -np.arange(10):
                trial = current + fraction*direction
                trial = np.array([np.clip(v, -np.inf if lo is None else lo, np.inf if hi is None else hi)
                                  for v, (lo, hi) in zip(trial, bounds)])
                if not engine.obj.base.state(trial[:engine.obj.size])['ephemeris_valid']:
                    continue
                new_value, new_gradient = engine.obj.evaluate(trial)
                new_pg, _ = projected_gradient(trial, new_gradient, bounds, scale)
                if new_value <= value+1e-7 and np.max(abs(new_pg)) < norm:
                    current = trial; accepted = True; break
            if not accepted:
                break
        result = engine.fit(point, label+'-exact-hessian-check', force_start=current)
        if result['success']:
            return result
        raise RuntimeError(f'Unconverged {scan} {case_id} {arm} {label}: {result["nuisance_gradient"]}')

    roof = fitted([0., 0.], 'capture-roof', engine.initial)
    cells = []
    for i, point in enumerate(design()):
        r = fitted(point, f'sample-{i}')
        cells.append(dict(point_km=point, objective=r['objective']))
    starts = [np.zeros(2)]
    for r in sorted(cells, key=lambda r: r['objective']):
        p = np.array(r['point_km'])
        if all(np.linalg.norm(p - s) > .45 for s in starts):
            starts.append(p)
        if len(starts) == 3:
            break

    def objective(x):
        radius = np.linalg.norm(x)
        point = x if radius <= 2 else x * (2 / radius)
        r = fitted(point)
        gradient = np.array(r['gradient_per_km'])
        if radius > 2:
            u = x / radius
            gradient = (2 / radius) * (gradient - u * (u @ gradient)) + 2000 * (radius - 2) * u
        return r['objective'] + 1000 * max(0., radius - 2) ** 2, gradient

    trials = []
    for start in starts:
        opt = minimize(objective, start, jac=True, method='SLSQP', bounds=[(-2, 2)] * 2,
            constraints=[dict(type='ineq', fun=lambda x: 4 - x @ x, jac=lambda x: -2*x)],
            options=dict(maxiter=35, ftol=1e-7))
        p = opt.x * min(1., 2 / max(np.linalg.norm(opt.x), 1e-10))
        r = fitted(p)
        trials.append(dict(start_km=start, point_km=p, objective=r['objective'], success=bool(opt.success),
                           message=str(opt.message), iterations=int(opt.nit)))
    # Include every converged sampled/profile point, not just optimizer endpoints.
    best = min((r for r in engine.cache.values() if r['success']), key=lambda r: r['objective'])
    point = np.array([best['east_m'], best['north_m']]) / 1000
    best = fitted(point, 'best-roof-restart', roof['vector'])
    neighbors = []
    for j in range(8):
        p = point + .025 * np.array([np.sin(j*np.pi/4), np.cos(j*np.pi/4)])
        if np.linalg.norm(p) <= 2:
            r = fitted(p, 'neighbor-25m')
            neighbors.append(dict(point_km=p, delta_score=r['objective'] - best['objective']))
    finite_gradient = []
    for axis in (0, 1):
        shift = np.eye(2)[axis] * .01
        high = fitted(shift, 'gradient-plus-10m', roof['vector'])
        low = fitted(-shift, 'gradient-minus-10m', roof['vector'])
        finite_gradient.append((high['objective'] - low['objective']) * 5.)
    gradient = np.array(roof['gradient_per_km']) / 10
    result = dict(scan=scan, arm=arm, case_id=case_id, subset=subset,
        roof=roof, best=best, cells=cells, trials=trials, neighbors_25m=neighbors,
        gradient_per_100m=gradient, gradient_fd_10m=finite_gradient,
        gradient_strength=float(np.linalg.norm(gradient)),
        gradient_strength_per_1000_windows=float(np.linalg.norm(gradient) * 1000 / subset['n_windows']),
        distance_m=float(np.linalg.norm(point) * 1000), east_m=best['east_m'], north_m=best['north_m'],
        boundary_limited=bool(np.linalg.norm(point) > 1.999),
        delta_score=best['objective'] - roof['objective'],
        minimum_neighbor_delta=min((r['delta_score'] for r in neighbors), default=0.),
        successful_starts=sum(r['success'] for r in trials), elapsed_s=time.monotonic()-started,
        scope='Best found within 2 km of capture roof; three-start local search, not a global certificate.')
    save(target, result)
    print('CASE_DONE', scan, case_id, arm, 'distance', round(result['distance_m']), 'gradient', np.round(gradient, 3), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('stage', choices=['prepare', 'run'])
    parser.add_argument('--workers', type=int, default=6); parser.add_argument('--case', nargs=3)
    args = parser.parse_args()
    if args.stage == 'prepare':
        prepare(); return
    if args.case:
        run_case(tuple(args.case)); return
    tasks = [(s, a, c) for s in 'AB' for a in ('fitted-c', 'zero-c')
             for c in ['all-100'] + [f'{m}-{int(f*100)}' for m in METHODS for f in FRACTIONS[:-1]]]
    failures = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_case, task): task for task in tasks}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as error:
                failures.append(dict(task=futures[future], error=repr(error)))
                print('CASE_FAILED', failures[-1], flush=True)
    save(OUT / 'run-status.json', dict(tasks=tasks, failures=failures))


if __name__ == '__main__':
    main()
