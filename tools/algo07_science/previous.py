"""Frozen ALGO07 science; source provenance is recorded in origin_manifest.json."""
import time
import numpy as np
from scipy.optimize import minimize
from .diagnose import objective, error
from .diagnose import build
from phase_reference_checks import phase_refresh
from probe_algo03_feasible_recovery import gate_slacks
from audit_explicit_phase_endpoint import exact_gate_replay
from algo06_science.position import family_score
from debug_fast_graph_unassociated import memberships
from inactive_graph_fragment import original_graph_view
from ds23_feasible_position import feasible_fit
from prototype_dsx01_continuous_position import latlon


def fit(d,z,arm,start,constrained=False,rounds=15):
    reference=d['problems'][arm][0].reference.copy();x=np.asarray(start);history=[];tic=time.monotonic()
    for epoch in range(rounds):
        p,dd=build(d,z,arm,reference)
        fun=lambda v:objective(p,dd,v)
        if constrained:
            opt=feasible_fit(fun,lambda v:list(gate_slacks(p,v,dd['entries']).values()),x,[-12.5]*2,[12.5]*2,iterations=40)
            x=np.asarray(opt['parameters']);success=opt['solver_success'];message=opt['solver_message'];nfev=opt['evaluations']
        else:
            opt=minimize(fun,x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,options=dict(maxiter=35,maxfun=140,eps=.001,ftol=1e-10,gtol=1e-4,maxls=15))
            x=opt.x;success=bool(opt.success);message=str(opt.message);nfev=int(opt.nfev)
        updated,check=phase_refresh(p.state(x)['phases'][p.labels],reference,limit_s=30)
        history.append(dict(x=x,success=success,message=message,nfev=nfev,**check))
        if check['phase_change_s']<=.01:break
        if epoch<rounds-1:reference=updated
    c=p.calculate(x);slacks=gate_slacks(p,x,dd['entries']);bad={k:v for k,v in slacks.items() if v<0}
    exact=[]
    for j in sorted({r['candidate_index'] for r,sl in zip(p.rows,p.slices) if p.keep[sl].any()}):
        p.explicit_phase_family=j;v=exact_gate_replay(p,x,dd['entries']);exact.append(dict(norad=int(p.scan.norads[j]),all_pass=v['all_pass'],failed={k:v for k,v in v['all_gate_slacks'].items() if v<0},maximum_difference_hz=v['maximum_linearization_difference_hz']))
    if hasattr(p,'explicit_phase_family'):del p.explicit_phase_family
    _,fd=family_score(dd['families'],dd,p,x,details=True)
    mixture_pass=all(g['compatible'] for f in fd for g in f['gates'])
    _,_,_,owners=memberships(original_graph_view(p,len(p.scan.index)),x,dd['entries'])
    for f in dd['families']:
        for e in f.entries:owners.update({o:e['norad'] for o in e['observation_ids']})
    before=z['baseline_owners'][arm]
    lost=[o for o in before if o not in owners];added=[o for o in owners if o not in before]
    changed=[o for o,n in before.items() if o in owners and owners[o]!=n]
    allpass=not bad and all(r['all_pass'] for r in exact) and mixture_pass
    params=[];begin=p.hardware.shape[1]+p.smooth.shape[1]
    for k,j in enumerate(p.labels):
        orb=c['coefficient'][begin+len(p.labels)+3*p.supported.index(j):begin+len(p.labels)+3*p.supported.index(j)+3] if j in p.supported else []
        params.append(dict(norad=int(p.scan.norads[j]),phase_s=float(p.state(x)['phases'][j]),phase_sigma_s=float(p.phase_sigma[k]),orbital_standardized=orb))
    tracks=[]
    for r,i,sl in zip(p.rows,p.members,p.slices):
        use=p.keep[sl]
        if not use.any():continue
        t=p.scan.tracks[i];tracks.append(dict(component=r['component'],norad=r['candidate_norad'],receiver=t['receiver'],channel=t['channel'],times_s=t['times'][use],values_hz=p.values[sl][use],residual_hz=c['conditional_residual_hz'][sl][use],observation_ids=[o for o,u in zip(t['observation_ids'],use) if u]))
    return dict(x=x,latlon=latlon(x),error_m=error(x),objective=fun(x),rms_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
        history=history,reference=reference,phase_closed=check['phase_change_s']<=.01,optimizer_success=success,all_gates_pass=allpass,
        failed_gates=bad,exact=exact,mixture_gates_pass=mixture_pass,active_points=int(p.keep.sum()),seconds=time.monotonic()-tic,
        lost_ids=lost,added_ids=added,reassigned_ids=changed,proposed_owners=owners,parameters=params,tracks=tracks,
        qualified=bool(allpass and check['phase_change_s']<=.01 and success and not lost),
        qualification_scope='RF/phase/optimizer/orbit/ownership screening; not independent identity validation or complete production acceptance')
