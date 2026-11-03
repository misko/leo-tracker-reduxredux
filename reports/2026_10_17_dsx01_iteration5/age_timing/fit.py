"""Same bounded profile/search policy, with an explicit prior-aware profile port."""

import time

import numpy as np
from scipy.optimize import minimize


class BudgetExpired(Exception):
    pass


def fit(context,*,profile_factory,refitter=None,max_evaluations=1000,max_seconds=120):
    if refitter is None:
        from common import refit
        refitter=refit
    begun=time.monotonic()
    deadline=min(begun+max_seconds,getattr(context,'deadline',float('inf')))
    v,n=context.vector.copy(),context.nuisance.copy()
    count=0
    projections=0
    rounds=[]
    current=float('inf')
    for _iteration in range(2):
        if count>=max_evaluations*.45 or time.monotonic()>=begun+max_seconds*.55:
            break
        profile=profile_factory(context,v,n)
        count+=1
        current=profile.initial_objective
        proposals=profile.search(deadline=min(deadline,begun+max_seconds*.55))
        projections+=profile.projections
        trials=[]
        for proposal in proposals[:12]:
            if count>=max_evaluations*.45 or time.monotonic()>=begun+max_seconds*.65:
                break
            tau=v[7]+context.model.basis@v[8:]
            tau[proposal['index']]=proposal['timing_s']
            vv=v.copy()
            vv[7]=tau.mean()
            vv[8:]=context.model.basis.T@(tau-vv[7])
            if abs(vv[7])>10:
                continue
            tail_start=context.model.base_nuisance_count
            limits=context.model.group_limits[context.model.original.group_count:]
            best=[float('inf'),n.copy()]
            local=0
            allowance=min(22,max_evaluations-count)
            def objective(tail, _allowance=allowance, _n=n, _start=tail_start,
                          _v=vv, _best=best):
                nonlocal count,local
                if local>=_allowance or time.monotonic()>=deadline:
                    raise BudgetExpired()
                nn=_n.copy()
                nn[_start:]=tail
                e=context.model.evaluate_joint(_v,nn)
                count+=1
                local+=1
                if e[0]<_best[0]:
                    _best[:]=[float(e[0]),nn.copy()]
                return e[0],e[2][_start:]
            try:
                if len(limits):
                    minimize(objective,n[tail_start:],jac=True,method='L-BFGS-B',
                        bounds=list(zip(-limits,limits,strict=True)),
                        options={'maxiter':20,'maxfun':allowance,'ftol':1e-10})
                else:
                    objective(np.empty(0))
            except BudgetExpired:
                pass
            accepted=best[0]<current-1e-7
            trials.append(dict(proposal=proposal,
                               exact_objective=best[0] if np.isfinite(best[0]) else None,
                               accepted=accepted,evaluations=local))
            if accepted:
                v,n,current=vv,best[1],best[0]
        rounds.append(dict(initial_objective=profile.initial_objective,profile_proposals=proposals,trials=trials))
    remaining=max_evaluations-count
    polish={}
    if remaining>0 and time.monotonic()<deadline:
        solved=refitter(context,v,n,max_evaluations=remaining,
                     max_seconds=max(.01,deadline-time.monotonic()),fixed_c=context.fixed_c)
        polish=solved['diagnostics']
        count+=polish['evaluations']
        if polish['objective']<=current+1e-7:
            v,n=solved['vector'],solved['nuisance']
            current=polish['objective']
    return dict(vector=v,nuisance=n,diagnostics=dict(
                method='exact-signed-all-point-timing-profiles',
                evaluations=count,orbit_projection_calls=projections,rounds=rounds,
                objective=current,polish=polish,elapsed_seconds=time.monotonic()-begun,
                qualification='Fixed-bank physical model and original classification. '
                    'Profile columns are independent single-satellite exact objective changes.'))
