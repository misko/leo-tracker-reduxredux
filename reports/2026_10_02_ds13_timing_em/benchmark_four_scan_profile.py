"""Bounded numerical check of an alternative nuisance optimizer, same loss."""
import json,time
import numpy as np
from compare_four_scans import OUTPUT,ROOT


def run():
    import prepare_scans as prep
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from rf_calibration_diagnostic import CalibrationObjective
    from position_profile_grid import run_profile
    from scipy.optimize import minimize
    from pathlib import Path
    prep.ROOT=OUTPUT;sid='scan-fw-ebe22947697c8bf8';directory=OUTPUT/'comparison-v2'/sid
    _,data=prep.load_scan(sid);bundle=OUTPUT/'scans'/sid
    seed=json.loads((bundle/'seed.json').read_text());manifest=json.loads((bundle/'bundle.json').read_text())
    sats=np.array(seed['satellites']);tle=json.loads((ROOT/'later-tle-timing-aligned-v2/receipt.json').read_text())['latest_snapshot']['path']
    catalogue=parse_element_sets(Path(tle).read_text());lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    indices=[lookup[int(n)] for n in data.numbers[sats]]
    p,v,valid=propagate_candidate_states(catalogue,indices,manifest['origin_utc_ns'],data.nodes,np.array([0.]))
    assert list(valid)==indices
    data.position=data.position.copy();data.velocity=data.velocity.copy();data.position[sats]=p[:,0];data.velocity[sats]=v[:,0]
    start=json.loads((directory/'fit-0002.json').read_text());target=json.loads((directory/'fit-0003.json').read_text())
    obj=CalibrationObjective(data,np.asarray(start['parameters']),sats,False,30)
    obj.likelihood.detection_probability=.8/len(sats)
    vector=np.array(start['vector']);vector[:2]=target['parameters'][:2];scale=obj.scale
    bounds=list(obj.bounds);bounds[:2]=[(x,x) for x in vector[:2]]
    def fun(x):
        value,g=obj.evaluate(x*scale);return value,g*scale
    begin=time.monotonic()
    res=minimize(fun,vector/scale,jac=True,method='L-BFGS-B',bounds=[(None if a is None else a/s,None if b is None else b/s) for (a,b),s in zip(bounds,scale)],
        options=dict(maxiter=800,maxcor=30,gtol=5e-4,ftol=1e-15,maxls=20))
    warm_elapsed=time.monotonic()-begin
    fit=run_profile(data,start['parameters'],sats,start['rf_coefficient_hz_per_ghz'],vector[:2],
        probability_override=.8/len(sats),start_vector=res.x*scale,budget_s=8)
    print(dict(warm_s=warm_elapsed,total_s=time.monotonic()-begin,optimizer_success=bool(res.success),
        iterations=res.nit,success=fit['success'],objective_difference=fit['objective']-target['objective'],
        nuisance_gradient=fit['projected_nuisance_gradient_inf_norm']),flush=True)


if __name__=='__main__':run()
