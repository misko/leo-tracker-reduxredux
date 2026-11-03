"""Inspect SLSQP's terminal state separately from the fitter's best-so-far state."""
from dataclasses import replace
import numpy as np
import diagnose as d
import bounded_fit as solver


def check(obj,oracle,start,arm,fixed,xy,radius,width):
    original=solver.minimize;terminal=[]
    def capture(*args,**kwargs):
        r=original(*args,**kwargs);terminal.append(r)
        return r
    solver.minimize=capture
    try:
        fit=d.ORIGINAL_FIT(obj,start,rf_arm=arm,fixed_position=fixed,
            maximum_seconds=20.,maximum_iterations=600,slope_half_width_hz_s=width,
            local_center=None if fixed else np.asarray(xy),local_radius_km=None if fixed else radius)
    finally:solver.minimize=original
    scale=np.r_[1.,1.,200.,2.,200.,2.,200.,np.ones(obj.size-7)]
    free=[i for i in range(obj.size) if not (fixed and i<2) and not (arm=='zero-c' and i==6)]
    out=dict(returned=dict(objective=fit.objective,stationarity=fit.stationarity,
                          converged=fit.converged,stop_reason=fit.stop_reason))
    if terminal:
        v=np.asarray(start).copy();v[free]=terminal[-1].x*scale[free]
        if arm=='zero-c':v[6]=0.
        raw,gradient,_=oracle.evaluate(v);cost,extra=d.independent_penalty(v,obj.spec)
        gradient=gradient+extra
        if fixed:gradient[:2]=0.
        audit=d.engine.audit(oracle,v,gradient,arm,[0.,0.] if fixed else xy,
                             oracle.prior.radius_km if fixed else radius,width)
        out['terminal']=dict(vector=v,objective=raw+cost,objective_change=raw+cost-fit.objective,
            error_km=d.error(obj.prior,v),optimizer_success=bool(terminal[-1].success),**audit)
    return out


def main():
    for label in ['N39','N49']:d.engine.CONTEXT[label]=d.run.data.load(label)
    out=[]
    for r in d.read(d.HERE/'probes.json')['outputs']:
        if r['kind']!='pipeline' or r['mode']!='calibration_retry':continue
        label,phase,xy=r['label'],r['phase'],r['point'];cfg=d.CONFIGS[phase]
        _,obs,bank,prior,score=d.engine.CONTEXT[label]
        score=replace(score,relative_sigma_s=cfg['sigma'])
        point=d.read(d.source(label,phase)/'points'/f'{xy[0]:g}_{xy[1]:g}.json')
        region=d.read(d.region_path(d.HERE/'calibration_retry/results'/label/phase,xy,r['radius_km']))
        subset=bank.select(point['bootstrap']['satellite_indices'])
        post=point['fit']['converged']
        baseline=np.asarray(region['calibration']['correction']['values_hz']) if post else None
        oracle=d.run.BASE_ORACLE(obs,subset,prior,score,receiver_baseline_hz=baseline)
        obj=d.PenalizedObjective(d.run.BASE_NATIVE(obs,subset,prior,score,receiver_baseline_hz=baseline),cfg['slope_prior'])
        result=check(obj,oracle,np.asarray(point['fit']['vector']),'fitted-c',True,xy,r['radius_km'],cfg['width'])
        out.append(dict(label=label,phase=phase,point=xy,stage='postfit' if post else 'prefit',**result))
    label,phase,xy,radius='N49','gaussian60',[-57.5,-77.5],25.
    _,obs,bank,prior,score=d.engine.CONTEXT[label];cfg=d.CONFIGS[phase]
    score=replace(score,relative_sigma_s=cfg['sigma'])
    region=d.read(d.region_path(d.source(label,phase),xy,radius))
    subset=bank.select(region['association']['selected_indices'])
    baseline=np.asarray(region['calibration']['receiver_baseline_hz'])
    oracle=d.run.BASE_ORACLE(obs,subset,prior,score,receiver_baseline_hz=baseline)
    obj=d.PenalizedObjective(d.run.BASE_NATIVE(obs,subset,prior,score,receiver_baseline_hz=baseline),cfg['slope_prior'])
    start=min((c for c in region['candidates'] if c['arm']=='fitted-c' and c['feasible']),key=lambda c:c['selection_score'])['vector']
    out.append(dict(label=label,phase=phase,point=xy,stage='final',**check(obj,oracle,np.asarray(start),'fitted-c',False,xy,radius,cfg['width'])))
    d.engine.write(d.HERE/'terminal_audit.json',dict(outputs=out))
    for r in out:
        print(r['label'],r['phase'],r['point'],r['stage'],'returned',r['returned'],
            'terminal',{k:v for k,v in r.get('terminal',{}).items() if k!='vector'},flush=True)


if __name__=='__main__':main()
