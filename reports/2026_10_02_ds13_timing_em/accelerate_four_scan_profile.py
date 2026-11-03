"""Numerical warm start for slow scan 2; unchanged model and convergence gate."""
import json,time
import numpy as np
from compare_four_scans import OUTPUT,run
import position_profile_grid as profile
from rf_calibration_diagnostic import CalibrationObjective
from timing_model import DeadlineReached
from finite_set_fit import snapshot_files,assert_snapshot_unchanged
from scipy.optimize import minimize
from truth_start_diagnostic import projected_gradient

original=profile.run_profile
diagnostics=[]
checkpoint=OUTPUT/'comparison-v2/scan2-original-minimum-checkpoint.json'
cache={}


def polish(objective,vector,bounds):
    """Newton on analytic nuisance gradients near numerical objective plateaus."""
    objective.base.deadline=time.monotonic()+10.
    current=vector.copy();scale=objective.scale
    for _ in range(2):
        value,g=objective.evaluate(current);projected,free=projected_gradient(current,g,bounds,scale)
        if np.max(np.abs(projected))<=5e-4:break
        indices=np.flatnonzero(free);h=1e-4;H=np.empty((len(indices),len(indices)))
        for j,k in enumerate(indices):
            delta=np.zeros(len(current));delta[k]=h*scale[k]
            gp=objective.evaluate(current+delta)[1]*scale
            gm=objective.evaluate(current-delta)[1]*scale
            H[:,j]=(gp[indices]-gm[indices])/(2*h)
        H=(H+H.T)/2
        if np.min(np.linalg.eigvalsh(H))<=0:break
        step=np.linalg.solve(H,-projected[indices]);trial=current.copy();trial[indices]+=step*scale[indices]
        if any((a is not None and x<a) or (b is not None and x>b) for x,(a,b) in zip(trial,bounds)):break
        trial_value,trial_g=objective.evaluate(trial)
        trial_projected,_=projected_gradient(trial,trial_g,bounds,scale)
        if trial_value>value+1e-7 or np.max(np.abs(trial_projected))>=np.max(np.abs(projected)):break
        current=trial
    return current


def accelerated(data,initial_parameters,satellites,rf_coefficient,position,probability_override=None,
                *,start_vector=None,budget_s=8.,**kwargs):
    started=time.monotonic()
    key=(tuple(map(int,satellites)),tuple(np.round(position,9)))
    if key in cache:
        fit=cache[key]
        diagnostics.append(dict(reused_checkpoint=True,success=fit['success'],objective=fit['objective']))
        return fit
    obj=CalibrationObjective(data,np.asarray(initial_parameters),np.asarray(satellites),False,12.)
    obj.likelihood.detection_probability=probability_override
    vector=obj.initial.copy() if start_vector is None else np.asarray(start_vector).copy()
    if start_vector is None:vector[obj.size:]=rf_coefficient
    # Preserve the better basin reached by the original Fisher iterations.
    # A cold L-BFGS start found a worse local basin; it is not substituted.
    if not diagnostics:vector=np.asarray(json.loads(checkpoint.read_text())['vector'])
    vector[:2]=position;scale=obj.scale;bounds=list(obj.bounds);bounds[:2]=[(x,x) for x in position]
    def fun(x):
        value,g=obj.evaluate(x*scale);return value,g*scale
    status='deadline'
    try:
        res=minimize(fun,vector/scale,jac=True,method='L-BFGS-B',
            bounds=[(None if a is None else a/s,None if b is None else b/s) for (a,b),s in zip(bounds,scale)],
            options=dict(maxiter=800,maxcor=30,gtol=5e-4,ftol=1e-15,maxls=20))
        status=str(res.message)
    except DeadlineReached:
        pass
    warm=vector if obj.best is None else obj.best['vector']
    fit=original(data,initial_parameters,satellites,rf_coefficient,position,
        probability_override=probability_override,start_vector=warm,budget_s=budget_s,**kwargs)
    if not fit['success'] and fit['projected_nuisance_gradient_inf_norm']<.05:
        try:
            polished=polish(obj,np.asarray(fit['vector']),bounds)
            fit=original(data,initial_parameters,satellites,rf_coefficient,position,
                probability_override=probability_override,start_vector=polished,budget_s=budget_s,**kwargs)
        except (DeadlineReached,np.linalg.LinAlgError):
            pass
    diagnostics.append(dict(elapsed_s=time.monotonic()-started,warm_status=status,success=fit['success'],objective=fit['objective']))
    return fit


if __name__=='__main__':
    from curvature_threshold_sweep import screen
    from compare_four_scans import THRESHOLDS
    out=OUTPUT/'comparison-v2';directory=out/'scan-fw-ebe22947697c8bf8'
    cache_path=out/'scan2-converged-profile-checkpoints.json'
    if not cache_path.exists():
        seed=json.loads((OUTPUT/'scans'/directory.name/'seed.json').read_text())
        tracks=json.loads((directory/'tracks.json').read_text())['tracks']
        sets={}
        for threshold in THRESHOLDS:
            kept=screen(seed['catalog_numbers'],tracks,threshold)['kept']
            chosen=tuple(s for n,s in zip(seed['catalog_numbers'],seed['satellites']) if n in kept)
            sets.setdefault(len(chosen),set()).add(chosen)
        records=[]
        for path in sorted(directory.glob('fit-*.json')):
            fit=json.loads(path.read_text());options=sets[len(fit['satellite_support'])]
            if fit['success'] and len(options)==1:
                records.append(dict(satellites=list(next(iter(options))),fit=fit))
        cache_path.write_text(json.dumps(records)+'\n')
    for record in json.loads(cache_path.read_text()):
        f=record['fit'];key=(tuple(record['satellites']),tuple(np.round(f['parameters'][:2],9)))
        if key not in cache or f['objective']<cache[key]['objective']:cache[key]=f
    hashes=snapshot_files([__file__,checkpoint,cache_path]);profile.run_profile=accelerated
    run(scan_index=2)
    assert_snapshot_unchanged(hashes)
    path=out/'worker-2.json';worker=json.loads(path.read_text())
    worker['source_hashes'].update(hashes)
    worker['numerical_warm_start']='L-BFGS-B on identical fixed-site nuisance loss, then original profile convergence verification; no model or threshold changes.'
    worker['warm_start_calls']=diagnostics
    path.write_text(json.dumps(worker,indent=2)+'\n')
