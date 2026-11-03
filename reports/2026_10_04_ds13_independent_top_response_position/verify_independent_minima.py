"""Independent restarts at the known roof and local-curvature checks."""
import json
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import numpy as np
from profile_top_2km import OUT, save
from profile_top_independent import load_engine


def verify(task):
    scan,arm=task
    r=json.loads((OUT/f'independent-{scan}-{arm}.json').read_text())
    e=load_engine(scan,arm)
    e.fit([0,0],'roof-from-independent-minimum',force_start=r['best']['vector'])
    raw=e.calls[-1]
    for _ in range(3):
        if raw['success']:break
        e.fit([0,0],'roof-from-independent-minimum-continue',force_start=raw['vector'])
        raw=e.calls[-1]
    output=dict(scan=scan,arm=arm,roof_restart_success=raw['success'],
        roof_restart_objective=raw['objective'],original_roof_objective=r['roof']['objective'],
        roof_restart_delta=raw['objective']-r['roof']['objective'],
        best_gradient_per_km=r['best']['gradient_per_km'],
        all_starts_converged=all(t['success'] for t in r['trials']),
        start_position_spread_m=max(np.linalg.norm(np.array(t['point_km'])-
            np.array([r['east_m'],r['north_m']])/1000)*1000 for t in r['trials']),
        minimum_neighbor_increase=min(n['delta_from_best'] for n in r['neighbors_25m']),
        boundary_limited=r['boundary_limited'])
    if len(r['neighbors_25m'])==8:
        # Profile Hessian from analytic gradients at opposite 25 m neighbor sites.
        gradients=[]
        for n in r['neighbors_25m']:
            key=tuple(np.round(np.array(n['point_km'])*1000,5))
            gradients.append(np.array(e.cache[key]['gradient_per_km']))
        h=np.column_stack(((gradients[2]-gradients[6])/.05,(gradients[0]-gradients[4])/.05))
        output['profile_hessian_eigenvalues_per_km2']=np.linalg.eigvalsh((h+h.T)/2)
    else:
        p=np.array([r['east_m'],r['north_m']]);u=p/np.linalg.norm(p)
        g=np.array(r['best']['gradient_per_km'])
        output['outward_radial_gradient_per_km']=float(u@g)
        output['tangential_gradient_per_km']=float(np.array([-u[1],u[0]])@g)
    return output


if __name__=='__main__':
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('fork')) as pool:
        results=list(pool.map(verify,[(s,a) for s in 'AB' for a in ('fitted-c','zero-c')]))
    save(OUT/'independent-audit.json',results)
    for r in results:print(json.dumps(r,default=lambda x:x.tolist()),flush=True)
