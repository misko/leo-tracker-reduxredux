"""Bounded independent-scan position and nuisance optimization.

Joint refers only to position+nuisance within ONE scan. Observations, candidate
bank, priors and budgets are matched between RF arms. Fixed-location probes
still profile nuisance; direct position steps avoid nesting whole nuisance fits
inside every line-search evaluation. Roof-conditioned memberships are not blind
localization. Best found is not a global certificate.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from cohort import ROOF, digest
from position_search import prepare, point_design
from constrained_fit import kkt_residual


def coordinate(point):
    from position_profile_grid import geodesic_position
    e,n=np.asarray(point)*1000
    return np.asarray(geodesic_position(*ROOF,np.degrees(np.arctan2(e,n)),np.hypot(e,n)))


def coordinate_jacobian(point):
    step=1e-3
    return np.column_stack([(coordinate(np.asarray(point)+axis*step)-coordinate(np.asarray(point)-axis*step))/(2*step)
                            for axis in np.eye(2)])


def disk_feasible(point):
    return bool(np.dot(point,point)<=4.+1e-8)


def fit(objective,start,point,budget_s=20.,fixed=False):
    from scipy.optimize import minimize,LinearConstraint
    from timing_model import DeadlineReached
    begun=time.monotonic()
    scale=np.asarray(objective.scale).copy()
    scale[:2]=1.
    z=np.asarray(start,float)/scale
    z[:2]=point
    bounds=[(None if lo is None else lo/s,None if hi is None else hi/s)
            for (lo,hi),s in zip(objective.bounds,scale)]
    bounds[:2]=[(v,v) for v in point] if fixed else [(-2.,2.)]*2
    for i,(lo,hi) in enumerate(bounds):
        if lo is not None:
            z[i]=max(z[i],lo)
        if hi is not None:
            z[i]=min(z[i],hi)
    matrix=np.zeros((len(objective.base.satellites),len(z)))
    matrix[:,6]=1.
    matrix[:,7:objective.size]=objective.base.basis
    matrix*=scale
    lower,upper=objective.base.minimum_shift_s+1e-6,objective.base.maximum_shift_s-1e-6
    # Blend toward zero to repair an initial common+relative bound violation,
    # preserving the zero-sum representation and common timing box constraint.
    totals=matrix@z
    factor=min(1.,upper/max(float(np.max(totals)),upper),lower/min(float(np.min(totals)),lower))
    z[6:objective.size]*=factor
    best=None
    objective.base.deadline=begun+budget_s
    def evaluate(z):
        nonlocal best
        vector=z*scale
        vector[:2]=coordinate(z[:2])
        value,gradient=objective.evaluate(vector)
        transformed=gradient*scale
        transformed[:2]=coordinate_jacobian(z[:2]).T@gradient[:2]
        feasible=disk_feasible(z[:2]) and np.all(matrix@z>=lower-1e-8) and np.all(matrix@z<=upper+1e-8)
        if feasible and value<1e25 and (best is None or value<best[0]):
            best=(float(value),z.copy())
        return value,transformed
    constraints=[LinearConstraint(matrix,lower,upper)]
    if not fixed:
        constraints.append(dict(type='ineq',fun=lambda v:4.-np.dot(v[:2],v[:2]),
                                jac=lambda v:np.r_[-2*v[:2],np.zeros(len(v)-2)]))
    try:
        result=minimize(evaluate,z,jac=True,method='SLSQP',bounds=bounds,constraints=constraints,
                        options=dict(maxiter=300,ftol=1e-9))
        status=str(result.message)
    except DeadlineReached:
        status='time_limit'
    if best is None:
        raise ValueError('no finite feasible direct-position iterate')
    objective.base.deadline=float('inf')
    value,z=best
    value,gradient=evaluate(z)
    audit_matrix,audit_lower,audit_upper=matrix, np.full(len(matrix),lower),np.full(len(matrix),upper)
    if not fixed and np.linalg.norm(z[:2])>=2.-1e-5:
        # Locally equivalent disk constraint has inward normal -2p.
        normal=np.r_[-2*z[:2],np.zeros(len(z)-2)]
        audit_matrix=np.vstack([matrix,normal])
        audit_lower=np.r_[audit_lower,normal@z]
        audit_upper=np.r_[audit_upper,np.inf]
    kkt=kkt_residual(gradient,z,bounds,audit_matrix,audit_lower,audit_upper)
    vector=z*scale
    vector[:2]=coordinate(z[:2])
    state=objective.base.state(vector[:objective.size])
    return dict(point_km=z[:2].tolist(),vector=vector.tolist(),objective=float(value),
                success=bool(kkt<=1e-3),kkt_residual=kkt,status=status,fixed_location=fixed,
                position_gradient_per_km=gradient[:2].tolist(),elapsed_s=time.monotonic()-begun,
                parameters=state['parameters'].tolist(),coefficient=float(vector[-1]))


def run(directory,method='alternatives',ranking='support',fraction=1.,smoke=False):
    data,meta=prepare(directory,method,ranking,fraction)
    from rf_calibration_diagnostic import CalibrationObjective
    root=directory/'position-direct-v1'/f'{method}-{ranking}-{int(round(fraction*100))}'
    root.mkdir(parents=True,exist_ok=True)
    signature=dict(inputs=meta,implementation=digest(Path(__file__).read_bytes()),
                   constrained_audit=digest(Path(__file__).with_name('constrained_fit.py').read_bytes()),
                   probe_budget_s=12.,search_budget_s=30.,scope=__doc__)
    outcomes={}
    for arm in ('fitted-c','zero-c'):
        objective=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,8.)
        objective.base.minimum_shift_s=max(objective.base.minimum_shift_s,-20.)
        objective.base.maximum_shift_s=min(objective.base.maximum_shift_s,20.)
        if arm=='zero-c':
            objective.bounds[-1]=(0.,0.)
        initial=objective.initial.copy()
        initial[-1]=meta['seed_coefficient'] if arm=='fitted-c' else 0.
        records=[]
        def saved_fit(name,start,point,budget,fixed):
            path=root/f'{arm}-{name}.json'
            if path.exists():
                saved=json.loads(path.read_text())
                if saved['signature']!=signature:
                    raise ValueError('direct position cache mismatch')
                result=saved['result']
            else:
                result=fit(objective,start,point,budget,fixed)
                with path.open('x') as stream:
                    json.dump(dict(signature=signature,result=result),stream,allow_nan=False)
            records.append(result)
            print('DIRECT',directory.name,arm,name,round(result['objective'],3),result['success'],flush=True)
            return result
        roof=saved_fit('roof',initial,[0.,0.],30.,True)
        design=point_design()
        for i,point in enumerate(design[1:3] if smoke else design[1:]):
            saved_fit(f'probe-{i:02d}',roof['vector'],point,12.,True)
        if smoke:
            continue
        ranked=sorted(records,key=lambda r:r['objective'])
        starts=[roof]
        for result in ranked:
            if all(np.linalg.norm(np.asarray(result['point_km'])-other['point_km'])>.4 for other in starts):
                starts.append(result)
            if len(starts)==3:
                break
        for i,start in enumerate(starts):
            saved_fit(f'search-{i}',start['vector'],start['point_km'],30.,False)
        best=min(records,key=lambda r:r['objective'])
        # Revisit both locations across nuisance basins before comparing scores.
        roof_check=saved_fit('roof-cross-basin',best['vector'],[0.,0.],30.,True)
        best_check=saved_fit('best-cross-basin',roof_check['vector'],best['point_km'],30.,True)
        best=min(records,key=lambda r:r['objective'])
        converged=[r for r in records if r['success']]
        outcomes[arm]=dict(best_found=best,best_converged=min(converged,key=lambda r:r['objective']) if converged else None,
                           roof=min([roof,roof_check],key=lambda r:r['objective']),records=records,
                           radius_m=float(1000*np.linalg.norm(best['point_km'])),
                           boundary=bool(np.linalg.norm(best['point_km'])>1.999),
                           claim='Best feasible sampled/optimized score; inspect convergence flags, not global certification.')
    if not smoke:
        (root/'summary.json').write_text(json.dumps(dict(signature=signature,arms=outcomes),indent=2,allow_nan=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--method',choices=('greedy','replacement','alternatives'),default='alternatives')
    p.add_argument('--ranking',choices=('rms','support','glrt'),default='support')
    p.add_argument('--fraction',type=float,default=1.)
    p.add_argument('--smoke',action='store_true')
    a=p.parse_args()
    run(a.directory,a.method,a.ranking,a.fraction,a.smoke)
