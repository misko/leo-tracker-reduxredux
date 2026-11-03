"""Matched cross-noise starts and active-bound numerical polish; same objectives."""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
import owner_mixture_localization as experiment
from owner_mixture_localization import OwnerObjective,load,feasible_start,fit,best_record,logistic,serial,digest
from render_leave_one_satellite_out import check_stationarity

SOURCE=experiment.OUT
OUT=SOURCE/'polished'


def active_noise_bounds(obj,vector):
    """Temporarily hold outward-gradient active noise bounds during Newton polish.

Final convergence is always checked against the ORIGINAL inequalities.
This does not fix interior estimates or relax the stationarity tolerance.
"""
    original=list(obj.bounds);_,g=obj.evaluate(np.asarray(vector))
    bounds=list(original)
    for i in (-2,-1):
        lo,hi=bounds[i];value=vector[i]
        if lo!=hi and abs(value-hi)<1e-8 and g[i]<-1e-8:bounds[i]=(hi,hi)
        elif lo!=hi and abs(value-lo)<1e-8 and g[i]>1e-8:bounds[i]=(lo,lo)
    return original,bounds


def run(task):
    scan,arm=task;data,meta,_=load(scan)
    sources={mode:SOURCE/f'{scan}-{arm}-{mode}.json' for mode in ('fixed-noise','learned-noise')}
    originals={m:json.loads(p.read_text()) for m,p in sources.items()}
    for mode in ('fixed-noise','learned-noise'):
        target=OUT/sources[mode].name
        if target.exists():continue
        obj=OwnerObjective(data,meta['rf_center_hz'],arm,mode=='learned-noise');obj.base.deadline=float('inf')
        original=originals[mode];records=list(original['records'])
        other=originals['fixed-noise' if mode=='learned-noise' else 'learned-noise']['best']
        for stage,seed in [('cross-noise-start',other),('active-bound-polish',None)]:
            if seed is None:seed=best_record(records)
            start=np.r_[feasible_start(obj,seed,20.,arm),np.log(seed['sigma_hz']),seed['logit_inlier']]
            obj.base.deadline=float('inf')
            old_bounds=list(obj.bounds)
            if stage=='active-bound-polish':
                _,obj.bounds=active_noise_bounds(obj,start)
            r=fit(obj,start,seed['point_km'],10.,False,radius_km=4.)
            obj.bounds=old_bounds;obj.base.deadline=float('inf')
            score,kkt=check_stationarity(obj,r,4.)
            r.update(stage=stage,coefficient=r['vector'][obj.size],sigma_hz=np.exp(r['vector'][-2]),
                     logit_inlier=r['vector'][-1],inlier_probability=logistic(r['vector'][-1]),
                     objective=score,kkt_residual=kkt,success=kkt<=1e-3,
                     status='constrained_polish_converged' if kkt<=1e-3 else r['status'])
            records.append(r)
        best=best_record(records);score,kkt=check_stationarity(obj,best,4.);r=obj.likelihood.last_result
        result=dict(original,best=best,records=records,objective=score,distance_m=1000*np.linalg.norm(best['point_km']),
            converged=bool(kkt<=1e-3 and not best['fixed_location']),boundary=np.linalg.norm(best['point_km'])>=3.9999,
            strong_owner_windows=int(sum(r['inlier_weight']>.5)),owner_visible_windows=int(sum(r['owner_visible'])),
            median_owner_absolute_residual_hz=float(np.median(abs(r['residual_hz']))),
            owner_rms_hz=float(np.sqrt(np.mean(r['residual_hz']**2))),
            timing_prior_nll=obj.base.penalty(np.asarray(best['vector'])[:obj.size])[0],kkt=kkt,
            polish_scope=__doc__,polish_maximum_budgets_s=[10.,10.],
            polish_sources_sha256={m:digest(p) for m,p in sources.items()},polish_implementation_sha256=digest(Path(__file__)))
        assert score<=original['objective']+1e-7
        target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
        print('POLISHED OWNER',scan,arm,mode,round(result['distance_m']),result['converged'],kkt,flush=True)


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(run,(s,a)) for s in experiment.SCANS for a in experiment.ARMS]):f.result()
    experiment.OUT=OUT;experiment.render()
