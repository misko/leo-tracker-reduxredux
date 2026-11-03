"""Matched bounded convergence continuation for the final-score sweep.

No objective, data, constraints or hyperparameter changes. Every case receives
up to 20 s SLSQP and 10 s Fisher, stopping at the same KKT <= 1e-3 criterion.
Preserve unpolished results and never choose by position truth.
"""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

import position_score_sweep as sweep
from position_direct import coordinate, coordinate_jacobian
from constrained_fit import kkt_residual
from timing_model import DeadlineReached

OUT = sweep.OUT/'polished'
BUDGETS = dict(slsqp_s=20., fisher_s=10.)


def slsqp_fit(obj, seed, budget_s, radius_km=4.):
    from scipy.optimize import minimize, LinearConstraint
    if budget_s <= 0 or radius_km <= 0:
        raise ValueError('Positive budget and radius required')
    begun = time.monotonic()
    scale = np.asarray(obj.scale).copy(); scale[:2] = 1.
    z = np.asarray(seed['vector'])/scale; z[:2] = seed['point_km']
    bounds = [(None if lo is None else lo/s, None if hi is None else hi/s)
              for (lo, hi), s in zip(obj.bounds, scale)]
    bounds[:2] = [(-radius_km, radius_km)]*2
    matrix = np.zeros((len(obj.base.satellites), len(z)))
    matrix[:, 6] = 1.; matrix[:, 7:obj.size] = obj.base.basis; matrix *= scale
    lower, upper = obj.base.minimum_shift_s+1e-6, obj.base.maximum_shift_s-1e-6
    best = None
    def evaluate(point):
        nonlocal best
        vector = point*scale; vector[:2] = coordinate(point[:2])
        value, g = obj.evaluate(vector)
        gradient = g*scale; gradient[:2] = coordinate_jacobian(point[:2]).T@g[:2]
        feasible = (np.linalg.norm(point[:2]) <= radius_km+1e-9
            and np.all(matrix@point >= lower-1e-9) and np.all(matrix@point <= upper+1e-9)
            and all((lo is None or v >= lo-1e-9) and (hi is None or v <= hi+1e-9)
                    for v, (lo, hi) in zip(point, bounds)))
        if feasible and np.isfinite(value) and value < 1e25 and (best is None or value < best[0]):
            best = (float(value), point.copy())
        return value, gradient
    obj.base.deadline = float('inf')
    evaluate(z)
    if best is None: raise ValueError('No feasible initial point')
    obj.base.deadline = begun+budget_s
    constraints = [LinearConstraint(matrix, lower, upper),
        dict(type='ineq', fun=lambda v: radius_km**2-np.dot(v[:2],v[:2]),
             jac=lambda v: np.r_[-2*v[:2],np.zeros(len(v)-2)])]
    try:
        result = minimize(evaluate, z, jac=True, method='SLSQP', bounds=bounds,
                          constraints=constraints, options=dict(maxiter=300, ftol=1e-11))
        status = str(result.message)
    except DeadlineReached:
        status = 'time_limit'
    obj.base.deadline = float('inf')
    _, z = best
    value, g = evaluate(z)
    m, lo, hi = matrix, np.full(len(matrix),lower), np.full(len(matrix),upper)
    if np.linalg.norm(z[:2]) >= radius_km-1e-5:
        normal = np.r_[-2*z[:2],np.zeros(len(z)-2)]
        m=np.vstack([m,normal]);lo=np.r_[lo,normal@z];hi=np.r_[hi,np.inf]
    kkt=float(kkt_residual(g,z,bounds,m,lo,hi))
    vector=z*scale;vector[:2]=coordinate(z[:2])
    return dict(point_km=z[:2].tolist(),vector=vector.tolist(),objective=float(value),
        success=kkt<=1e-3,kkt_residual=kkt,status=status,fixed_location=False,
        parameters=obj.base.state(vector[:obj.size])['parameters'].tolist(),
        coefficient=float(vector[-1]),elapsed_s=time.monotonic()-begun,
        stage='matched-slsqp-continuation')


def run(task):
    scan, arm, mode = task
    source=sweep.OUT/'final'/f'{scan}-{arm}-{mode}.json';target=OUT/source.name
    if target.exists():
        r=json.loads(target.read_text())
        assert r['continuation']['source_sha256']==sweep.digest(source)
        assert r['continuation']['implementation_sha256']==sweep.digest(Path(__file__))
        return str(target)
    r=json.loads(source.read_text())
    data,saved,_,_,_=sweep.inputs(scan)
    obj=sweep.objective(data,saved,arm,mode)
    for stage in ['slsqp','fisher']:
        best=sweep.best_record(r['records'])
        if sweep.finish(obj,data,best)['converged']:break
        if stage=='slsqp':new=slsqp_fit(obj,best,BUDGETS['slsqp_s'])
        else:
            new=sweep.fit(obj,np.array(best['vector']),best['point_km'],BUDGETS['fisher_s'],False,radius_km=4.)
            new['stage']='matched-fisher-continuation'
        r['records'].append(new)
    best=sweep.best_record(r['records'])
    assert best['objective']<=r['objective']+1e-7
    r['continuation']=dict(scope=__doc__,source_sha256=sweep.digest(source),
        implementation_sha256=sweep.digest(Path(__file__)),maximum_budgets_s=BUDGETS,
        original_error_m=r['distance_m'],original_converged=r['converged'])
    common=sweep.finish(sweep.objective(data,saved,arm,'C1'),data,best)
    r.update(best=best,timing=sweep.old.previous.timing_and_gradient(obj,best),
        common_reference_data_nll=common['data_nll'],common_reference_objective=common['objective'],
        **sweep.finish(obj,data,best))
    sweep.save(target,r)
    print('POLISHED',scan,arm,mode,round(r['distance_m']),'m','KKT',round(r['kkt'],5),flush=True)
    return str(target)


def report():
    rows=sweep.audit('polished')
    for r in rows:
        p=sweep.OUT/'final'/f'{r["scan"]}-{r["arm"]}-{r["mode"]}.json'
        assert r['continuation']['source_sha256']==sweep.digest(p)
        assert r['continuation']['implementation_sha256']==sweep.digest(Path(__file__))
        assert r['continuation']['maximum_budgets_s']==BUDGETS
        assert r['cross_sources']==sweep.initial_pool(r['scan'])[1]
    sweep.report('polished')
    path=OUT/'report.html'
    path.write_text(path.read_text().replace('<h2>Frozen settings</h2>',
        '<p>Convergence continuation: every case offered up to 20 s SLSQP + 10 s Fisher, stopping early at KKT ≤ 0.001. No new starts or model changes. Unconverged cases remain marked.</p><h2>Frozen settings</h2>'))
    historic=[]
    for r in rows:
        if r['mode'] not in ['C0','C1']:continue
        mode='baseline' if r['mode']=='C0' else 'relative-only'
        p=sweep.old.OUT/'final'/f'{r["scan"]}-{r["arm"]}-{mode}.json'
        prior=json.loads(p.read_text())
        historic.append(dict(scan=r['scan'],arm=r['arm'],control=r['mode'],
            previous_error_m=prior['distance_m'],rerun_error_m=r['distance_m'],
            objective_change=r['objective']-prior['objective'],
            previous_converged=prior['converged'],rerun_converged=r['converged']))
    sweep.csv_write(OUT/'control-restart-comparison.csv',historic)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scans',nargs='+',choices=sweep.SCANS,default=sweep.SCANS)
    parser.add_argument('--workers',type=int,default=12)
    parser.add_argument('--report-only',action='store_true')
    args=parser.parse_args()
    if args.report_only:report()
    else:
        jobs=[(s,a,m) for s in args.scans for m in sweep.SPECS for a in sweep.ARMS]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(run,j) for j in jobs]):future.result()
