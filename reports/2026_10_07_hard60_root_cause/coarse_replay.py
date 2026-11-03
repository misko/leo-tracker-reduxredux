"""Measure temporary clock excursions at identical coarse positions and seeds."""
import concurrent.futures as futures
from dataclasses import asdict,replace
import multiprocessing
import numpy as np
import diagnose as d


def probe(task):
    label,phase=task;cfg=d.CONFIGS[phase];spec=cfg['slope_prior']
    _,obs,bank,prior,score=d.engine.context(label,phase)
    score=replace(score,relative_sigma_s=2.)
    hard=d.read(d.source(label,'sigma2_60')/'points/-80_-80.json')
    point=d.read(d.source(label,phase)/'points/-80_-80.json')
    assert hard['bootstrap']==point['bootstrap']
    subset=bank.select(point['bootstrap']['satellite_indices'])
    base=d.run.BASE_NATIVE(obs,subset,prior,score)
    oracle=d.run.BASE_ORACLE(obs,subset,prior,score)
    obj=d.PenalizedObjective(base,spec)
    trace=[]
    class Traced:
        def __getattr__(self,name):return getattr(obj,name)
        def evaluate(self,vector):
            value,g,terms=obj.evaluate(vector)
            b=np.asarray(vector)[[3,5]];cost=d.penalty(b,spec)[0]
            trace.append(dict(objective=value,slopes_hz_s=b,slope_penalty=cost))
            return value,g,terms
    seed=np.asarray(point['bootstrap']['vector'])
    fit=d.ORIGINAL_FIT(Traced(),seed,fixed_position=True,rf_arm='fitted-c',
        maximum_seconds=5.,maximum_iterations=200,slope_half_width_hz_s=cfg['width'])
    raw,g,_=oracle.evaluate(fit.vector);cost,extra=d.independent_penalty(fit.vector,spec)
    np.testing.assert_allclose(raw+cost,fit.objective,atol=1e-6,rtol=0)
    hv=np.asarray(hard['fit']['vector'])
    hard_raw,_,_=oracle.evaluate(hv);hard_cost,_=d.independent_penalty(hv,spec)
    return dict(label=label,phase=phase,point=[-80.,-80.],identical_bootstrap=True,
        bootstrap_slopes_hz_s=seed[[3,5]],clipped_start_slopes_hz_s=np.clip(seed[[3,5]],-cfg['width'],cfg['width']),
        replay=asdict(fit),original_score=point['fit']['objective'],trace=trace,
        max_temporary_abs_slope_hz_s=float(max(abs(b) for r in trace for b in r['slopes_hz_s'])),
        penalty_active_evaluations=sum(r['slope_penalty']>1e-12 for r in trace),
        hard60_state_feasible=bool(max(abs(hv[[3,5]]))<=cfg['width']),
        hard60_state_target_objective=hard_raw+hard_cost,
        target_fit_excess_over_hard60_state=point['fit']['objective']-hard_raw-hard_cost)


def main():
    tasks=[('N64',p) for p in ['sigma2_60','smooth60','gaussian30']]+[('N49',p) for p in ['sigma2_60','hard30','gaussian60']]
    for label in ['N49','N64']:d.engine.CONTEXT[label]=d.run.data.load(label)
    with futures.ProcessPoolExecutor(max_workers=3,mp_context=multiprocessing.get_context('fork')) as pool:
        outputs=list(pool.map(probe,tasks))
    d.engine.write(d.HERE/'coarse_replay.json',dict(outputs=outputs))
    for r in outputs:
        print(r['label'],r['phase'],'score',r['original_score'],'replay',r['replay']['objective'],
              'temporary slope',r['max_temporary_abs_slope_hz_s'],'active penalty calls',r['penalty_active_evaluations'],
              'better Hard60 state gap',r['target_fit_excess_over_hard60_state'],flush=True)


if __name__=='__main__':main()
