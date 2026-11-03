"""N29: isolate the frozen piecewise clock correction, keeping its bank and starts."""
import concurrent.futures as futures
from dataclasses import asdict,replace
import multiprocessing
import numpy as np
import diagnose as d


def probe(task):
    xy,factor=task;label,phase='N29','sigma2_60';radius=25.
    _,obs,bank,prior,score=d.engine.context(label,phase)
    score=replace(score,relative_sigma_s=2.)
    region=d.read(d.region_path(d.source(label,phase),xy,radius))
    subset=bank.select(region['association']['selected_indices'])
    piecewise=np.asarray(region['calibration']['correction']['values_hz'])
    baseline=np.asarray(region['calibration']['receiver_baseline_hz'])+(factor-1)*piecewise
    obj=d.run.BASE_NATIVE(obs,subset,prior,score,receiver_baseline_hz=baseline)
    oracle=d.run.BASE_ORACLE(obs,subset,prior,score,receiver_baseline_hz=baseline)
    old={a:min((r for r in region['candidates'] if r['arm']==a and r['feasible'] and r['converged']),
               key=lambda r:r['selection_score']) for a in d.ARMS}
    starts={'association':region['association']['initial_vector'],
            'saved-zero-c':old['zero-c']['vector'],'saved-fitted-c':old['fitted-c']['vector']}
    outputs=[]
    for arm in d.ARMS:
        for name,start in starts.items():
            fit=d.ORIGINAL_FIT(obj,start,rf_arm=arm,maximum_seconds=20.,maximum_iterations=600,
                slope_half_width_hz_s=60.,local_center=np.asarray(xy),local_radius_km=radius)
            value,g,terms=oracle.evaluate(fit.vector)
            np.testing.assert_allclose(value,fit.objective,atol=1e-6,rtol=0)
            audit=d.engine.audit(oracle,fit.vector,g,arm,xy,radius,60.)
            assert audit['converged']==fit.converged
            outputs.append(dict(arm=arm,start=name,**asdict(fit),error_km=d.error(prior,fit.vector),
                selection_score=value+factor**2*region['calibration_penalty'],data_nll=float(terms.nll),
                timing_penalty=value-float(terms.nll),original_oracle_audit=audit))
    winners={a:min((r for r in outputs if r['arm']==a and r['converged']),key=lambda r:r['selection_score'],default=None) for a in d.ARMS}
    return dict(label=label,phase=phase,point=xy,factor=factor,outputs=outputs,winners=winners)


def main():
    d.engine.CONTEXT['N29']=d.run.data.load('N29')
    tasks=[(xy,factor) for xy in ([-87.5,-92.5],[-77.5,-72.5]) for factor in (1.,.5,0.)]
    outputs=[]
    with futures.ProcessPoolExecutor(max_workers=6,mp_context=multiprocessing.get_context('fork')) as pool:
        pending={pool.submit(probe,t):t for t in tasks}
        for f in futures.as_completed(pending):
            r=f.result();outputs.append(r)
            d.engine.write(d.HERE/'baseline_scale.json',dict(outputs=outputs))
            print(r['point'],r['factor'],[(a,None if w is None else (w['error_km'],w['selection_score'])) for a,w in r['winners'].items()],flush=True)
    print('COMPLETE 6 groups; both c arms; identical starting pool and budgets',flush=True)


if __name__=='__main__':main()
