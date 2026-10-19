"""Learn separate age/disagreement gain and floor from past TLE updates."""

import argparse
from pathlib import Path

import numpy as np

from learn_ds23_causal_phase_forecast import distribution_cost
from run_algo01_ds23_sample import read,sha,write


def phase_sigma(floor,gain,alignment,age,gap):
    d=np.asarray(alignment)*np.maximum(np.asarray(age),0)/np.maximum(np.asarray(gap),1)
    return np.clip(np.hypot(floor,gain*d),.02,15.)


def arrays(rows):
    target=np.array([r['next_innovation_s'] for r in rows])
    forecast=np.array([r['unit_forecast_s'] for r in rows])
    proxy=np.array([abs(r['old_middle_alignment_s'])*r['age_s']/r['epoch_gap_s'] for r in rows])
    base=np.array([r['predicted_sigma_s'] for r in rows])
    return target,forecast,proxy,base


def learn(rows):
    if len(rows)<30:return dict(fallback=True,floor_s=1.,gain=1.,shrinkage=0.,nu=None)
    y,p,d,base=arrays(rows);limit=np.minimum(15.,3*base)
    best=None
    for rho in (0.,.25,.5,.75,1.):
        error=y-np.clip(rho*p,-limit,limit)
        for nu in (None,3.,4.,8.,16.):
            def objective(z):
                floor,gain=np.exp(z)
                sigma=np.clip(np.hypot(floor,gain*d),.02,15)
                return float(np.sum(distribution_cost(error,sigma,1.,nu)))
            # The research environment has NumPy, without SciPy. A bounded
            # coarse grid followed by deterministic local grids is sufficient
            # for these two variance parameters and preserves reproducibility.
            bounds=np.log(np.array([[.02,2.],[.05,2.]]))
            point=None;value=float('inf')
            lo,hi=bounds[:,0].copy(),bounds[:,1].copy()
            for _ in range(5):
                axes=[np.linspace(lo[k],hi[k],7) for k in range(2)]
                for floor in axes[0]:
                    for gain in axes[1]:
                        z=np.array([floor,gain]);v=objective(z)
                        if v<value:point,value=z,v
                step=(hi-lo)/6
                lo=np.maximum(bounds[:,0],point-step)
                hi=np.minimum(bounds[:,1],point+step)
            if best is None or value<best['cost']:
                best=dict(shrinkage=rho,nu=nu,floor_s=float(np.exp(point[0])),
                          gain=float(np.exp(point[1])),cost=float(value),fallback=False)
    return best


def cost(rows,model):
    if not rows:return None
    y,p,d,base=arrays(rows);limit=np.minimum(15.,3*base)
    error=y-np.clip(model['shrinkage']*p,-limit,limit)
    sigma=np.clip(np.hypot(model['floor_s'],model['gain']*d),.02,15)
    return float(np.sum(distribution_cost(error,sigma,1.,model['nu'])))


def run(path):
    document=read(path);rows=document['transitions'];boundary=document['temporal_split_boundary_ns']
    train=[r for r in rows if r['validation_time_ns']<=boundary]
    validation=[r for r in rows if r['validation_time_ns']>boundary]
    prefix=learn(train);full=learn(rows)
    heldout=cost(validation,prefix)
    scalar=document['distribution_validation']['negative_twice_log_density']
    qualified=len(validation)>=30 and heldout is not None and heldout<scalar
    result=dict(case=document['case'],all_past_model=full,prefix_model=prefix,
        validation_transitions=len(validation),variance_law_heldout_cost=heldout,
        scalar_prior_heldout_cost=scalar,qualified_against_scalar_prior=qualified,
        GPS_or_radio_used=False,strictly_pre_RF=document['strictly_pre_RF'],
        all_past_history_forecast_sha256=sha(path),source_sha256=sha(Path(__file__)))
    output=path.with_name(path.stem.replace('_forecast','_variance_law')+'.json')
    write(output,result)
    print(document['case'],full,'qualified',qualified,'heldout',heldout,'scalar',scalar,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('forecast',type=Path)
    run(parser.parse_args().forecast)
