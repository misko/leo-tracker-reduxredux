"""Continue nuisance fits in <=0.5 km steps from the saved winner to reference."""
import concurrent.futures as futures
from dataclasses import asdict, replace
import multiprocessing
import numpy as np
import diagnose as d

TASKS = [('N29','sigma2_60',[-87.5,-92.5],25.),
         ('N29','sigma2_60',[-77.5,-72.5],25.),
         ('N05','gaussian60',[-82.5,-102.5],25.)]


def profile(task):
    label,phase,xy,radius=task
    _,obs,bank,prior,score=d.engine.context(label,phase)
    cfg=d.CONFIGS[phase];spec=cfg['slope_prior']
    region=d.read(d.region_path(d.source(label,phase),xy,radius))
    subset=bank.select(region['association']['selected_indices'])
    baseline=np.asarray(region['calibration']['receiver_baseline_hz'])
    score=replace(score,relative_sigma_s=cfg['sigma'])
    obj=d.PenalizedObjective(d.run.BASE_NATIVE(obs,subset,prior,score,receiver_baseline_hz=baseline),spec)
    oracle=d.run.BASE_ORACLE(obs,subset,prior,score,receiver_baseline_hz=baseline)
    truth=d.reference_point(prior,d.reference())
    constant=region['calibration_penalty']+d.penalty(np.asarray(region['calibration']['postfit']['vector'])[[3,5]],spec)[0]
    starts={a:min((r for r in region['candidates'] if r['arm']==a and r['feasible'] and r['converged']),
                  key=lambda r:r['selection_score']) for a in d.ARMS}
    steps=int(np.ceil(max(np.linalg.norm(np.asarray(r['vector'][:2])-truth) for r in starts.values())/.5))
    outputs=[]
    for arm in d.ARMS:
        selected=starts[arm];v=np.asarray(selected['vector']);origin=v[:2].copy()
        for index,alpha in enumerate(np.linspace(0,1,steps+1)):
            start=v.copy();start[:2]=origin*(1-alpha)+truth*alpha
            fit=d.ORIGINAL_FIT(obj,start,rf_arm=arm,fixed_position=True,
                maximum_seconds=10.,maximum_iterations=600,slope_half_width_hz_s=cfg['width'])
            v=fit.vector
            raw,gradient,terms=oracle.evaluate(v);cost,extra=d.independent_penalty(v,spec)
            np.testing.assert_allclose(raw+cost,fit.objective,rtol=0,atol=1e-6)
            free_grad=gradient+extra;free_grad[:2]=0.
            checked=d.engine.audit(oracle,v,free_grad,arm,[0.,0.],prior.radius_km,cfg['width'])
            assert checked['converged']==fit.converged
            outputs.append(dict(arm=arm,step=index,alpha=float(alpha),error_km=d.error(prior,v),
                score_delta=raw+cost+constant-selected['selection_score'],selection_score=raw+cost+constant,
                data_nll=float(terms.nll),timing_penalty=raw-float(terms.nll),slope_penalty=cost,
                signal_fraction=float(terms.responsibilities.sum()/len(obs.times_s)),
                **asdict(fit)))
        released=d.ORIGINAL_FIT(obj,v,rf_arm=arm,maximum_seconds=20.,maximum_iterations=600,
            slope_half_width_hz_s=cfg['width'],local_center=np.asarray(xy),local_radius_km=radius)
        value,gradient,_=oracle.evaluate(released.vector);cost,extra=d.independent_penalty(released.vector,spec)
        checked=d.engine.audit(oracle,released.vector,gradient+extra,arm,xy,radius,cfg['width'])
        np.testing.assert_allclose(value+cost,released.objective,rtol=0,atol=1e-6)
        assert checked['converged']==released.converged
        outputs.append(dict(arm=arm,step='release',error_km=d.error(prior,released.vector),
            score_delta=released.objective+constant-selected['selection_score'],**asdict(released)))
    return dict(label=label,phase=phase,point=xy,steps_per_arm=steps,outputs=outputs)


def main():
    for label in sorted({t[0] for t in TASKS}):d.engine.CONTEXT[label]=d.run.data.load(label)
    outputs=[]
    with futures.ProcessPoolExecutor(max_workers=3,mp_context=multiprocessing.get_context('fork')) as pool:
        for result in pool.map(profile,TASKS):
            outputs.append(result)
            d.engine.write(d.HERE/'profile_paths.json',dict(outputs=outputs))
            print('DONE',result['label'],result['point'],flush=True)
    print('COMPLETE',len(outputs),'profiles; both c arms; original likelihood checked',flush=True)


if __name__=='__main__':main()
