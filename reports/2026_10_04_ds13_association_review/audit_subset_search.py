"""Cross-restart roof and minimum nuisance fits after each completed search."""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
from scipy.optimize import minimize

from subset_position_search import OUT, SubsetEngine, save


def audit(path):
    r = json.loads(path.read_text())
    previous = r.get('cross_restart_audit')
    if previous and previous.get('version') == 2:
        return path.name
    if previous and not previous['roof_branch_changed'] and r['delta_score'] <= 0 and r['minimum_neighbor_delta'] >= -.001:
        previous['version'] = 2
        save(path, r)
        return path.name
    engine = SubsetEngine(r['scan'], r['arm'], r['subset'])

    def fit(point, label, start=None):
        for _ in range(3):
            result = engine.fit(point, label, force_start=start)
            if engine.calls[-1]['success']:
                return result
            start = engine.calls[-1]['vector']
        raise RuntimeError(f'Cross restart failed: {path.name} {label}')

    old_roof, old_best = r['roof'], r['best']
    roof = fit([0., 0.], 'audit-roof-from-best', old_best['vector'])
    point = np.array([old_best['east_m'], old_best['north_m']]) / 1000
    best = fit(point, 'audit-best-from-roof', roof['vector'])
    polished = False
    significant = roof['objective'] < old_roof['objective'] - 1e-6
    needs_search = significant or best['objective'] < old_best['objective'] - 1e-4 or bool(previous and previous['roof_branch_changed'])
    if needs_search:
        # Start from the lowest known point, which can now be the roof itself.
        best = min((row for row in engine.cache.values() if row['success']), key=lambda row: row['objective'])
        point = np.array([best['east_m'], best['north_m']]) / 1000
        evaluations = 0
        class SearchBudget(Exception):
            pass
        def objective(x):
            nonlocal evaluations
            evaluations += 1
            if evaluations > 60:
                raise SearchBudget()
            rad = np.linalg.norm(x); p = x if rad <= 2 else x * 2 / rad
            row = engine.fit(p, 'audit-polish')
            if not row['success']:
                row = fit(p, 'audit-polish-continue', row['vector'])
            g = np.array(row['gradient_per_km'])
            if rad > 2:
                u = x/rad; g = 2/rad*(g-u*(u@g)) + 2000*(rad-2)*u
            return row['objective'] + 1000*max(0., rad-2)**2, g
        try:
            opt = minimize(objective, point, jac=True, method='SLSQP', bounds=[(-2, 2)]*2,
                constraints=[dict(type='ineq', fun=lambda x: 4-x@x, jac=lambda x: -2*x)],
                options=dict(maxiter=20, ftol=1e-7))
            polished = dict(success=bool(opt.success), message=str(opt.message), evaluations=evaluations)
        except SearchBudget:
            polished = dict(success=False, message='60 profile-evaluation polish budget reached; retain best found', evaluations=evaluations)
        best = min((row for row in engine.cache.values() if row['success']), key=lambda row: row['objective'])
        point = np.array([best['east_m'], best['north_m']]) / 1000
    if significant:
        fd = []
        for axis in (0, 1):
            step = np.eye(2)[axis]*.01
            high = fit(step, 'audit-roof-gradient-plus', roof['vector'])
            low = fit(-step, 'audit-roof-gradient-minus', roof['vector'])
            fd.append((high['objective']-low['objective'])*5)
        r['gradient_fd_10m'] = fd
    if best['objective'] < old_best['objective'] - 1e-6:
        neighbors = []
        for j in range(8):
            p = point+.025*np.array([np.sin(j*np.pi/4), np.cos(j*np.pi/4)])
            if np.linalg.norm(p) <= 2:
                row = fit(p, 'audit-neighbor', best['vector'])
                neighbors.append(dict(point_km=p, delta_score=row['objective']-best['objective']))
        r['neighbors_25m'] = neighbors
        r['minimum_neighbor_delta'] = min((row['delta_score'] for row in neighbors), default=0.)
    # Never report a worse minimum than a point we have actually evaluated.
    known = min((row for row in engine.cache.values() if row['success']), key=lambda row: row['objective'])
    lower_after_neighbors = known['objective'] < best['objective'] - 1e-6
    if lower_after_neighbors:
        best = known
        point = np.array([best['east_m'], best['north_m']]) / 1000
    r['cross_restart_audit'] = dict(version=2, previous=previous,
        lower_point_after_neighbors=lower_after_neighbors,
        roof_score_change=roof['objective']-old_roof['objective'],
        best_score_change=best['objective']-old_best['objective'], roof_branch_changed=significant,
        old_roof_gradient_per_100m=r['gradient_per_100m'], polished=polished,
        old_distance_m=r['distance_m'])
    g = np.array(roof['gradient_per_km'])/10
    r.update(roof=roof, best=best, gradient_per_100m=g, gradient_strength=float(np.linalg.norm(g)),
        gradient_strength_per_1000_windows=float(np.linalg.norm(g)*1000/r['subset']['n_windows']),
        distance_m=float(np.linalg.norm(point)*1000), east_m=best['east_m'], north_m=best['north_m'],
        boundary_limited=bool(np.linalg.norm(point)>1.999), delta_score=best['objective']-roof['objective'])
    save(path, r)
    print('AUDITED', path.name, 'roof_change', r['cross_restart_audit']['roof_score_change'],
          'best_change', r['cross_restart_audit']['best_score_change'], flush=True)
    return path.name


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    files = sorted(OUT.glob('*-c.json'))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(audit, path) for path in files]):
            future.result()
