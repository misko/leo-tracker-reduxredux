"""Exact all-training-point coordinate timing profiles, with unchanged likelihood.

Unlike the frozen A proposal, every scored observation contributes signed
evidence. No arc cap, sampled-coherence threshold, window labels or new offsets.
"""
from __future__ import annotations

import time

import numpy as np
from scipy.optimize import minimize

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular, ALIAS_HZ
from leo.analysis.shared_scan_model import elevation_geometry, horizon_weight


def timing_vector(model,vector,times):
    v=np.array(vector,copy=True)
    v[7]=np.mean(times)
    v[8:]=model.basis.T@(times-v[7])
    return v


def timing_penalty_delta(tau,proposed,common_sigma,relative_sigma):
    """One independent candidate change per column, exact common/relative prior."""
    tau=np.asarray(tau)
    common=tau.mean()
    delta=np.asarray(proposed)-tau
    k=len(tau)
    return (.5*((common+delta/k)**2-common**2)/common_sigma**2
            +(delta*(tau-common)+.5*delta**2*(1-1/k))/relative_sigma**2)


class Profiles:
    """Vectorize K exact single-candidate objective comparisons per projection."""
    def __init__(self,context,vector,nuisance):
        self.context=context
        self.model=context.model
        self.vector=np.array(vector,copy=True)
        self.nuisance=np.array(nuisance,copy=True)
        model=self.model
        self.obs=model.scored_observations
        ev,details=model.evaluate_details(vector,nuisance)
        terms=ev[3]
        self.initial_objective=float(ev[0])
        self.initial_nll=float(terms.nll)
        self.fixed_penalty=float(ev[0]-terms.nll)
        self.tau=vector[7]+model.basis@vector[8:]
        self.q=details['detection_probability']
        self.sigma=details['sigma_hz']
        self.clutter=model.score.clutter_rate/ALIAS_HZ
        p=details['visibility_weight']*self.q[None,:]
        odds=p/(1-p)
        gaussian=np.exp(-.5*(terms.residual_hz/self.sigma[:,None])**2)/(self.sigma[:,None]*np.sqrt(2*np.pi))
        signal=odds*gaussian
        total=self.clutter+signal.sum(axis=1)
        normalizer=model.score.clutter_rate+odds.sum(axis=1)
        self.remaining_total=np.maximum(total[:,None]-signal,self.clutter)
        self.remaining_normalizer=np.maximum(normalizer[:,None]-odds,model.score.clutter_rate)
        correction=model.original.correction(vector,nuisance[:model.clock_count])[model.mask]
        self.measured=self.obs.measured_hz-correction
        self.projections=0

    def score(self,times):
        """Column k changes only satellite k; all other predictions stay fixed."""
        times=np.asarray(times,float)
        pred,_,_,_=predict_orbits(self.context.bank,self.obs,self.context.prior,
                                  self.vector[:2],times,derivatives=False)
        sine=elevation_geometry(self.context.bank,self.obs,self.context.prior,self.vector[:2],times)[0]
        visible=horizon_weight(sine,self.model.visibility_width)[0]
        p=visible*self.q[None,:]
        odds=p/(1-p)
        residual=circular(self.measured[:,None]-pred)
        gaussian=np.exp(-.5*(residual/self.sigma[:,None])**2)/(self.sigma[:,None]*np.sqrt(2*np.pi))
        nll=np.sum(np.log(self.remaining_normalizer+odds)-np.log(self.remaining_total+odds*gaussian),axis=0)
        self.projections+=1
        return nll+self.fixed_penalty+timing_penalty_delta(self.tau,times,
            self.model.score.common_sigma_s,self.model.score.relative_sigma_s)

    def search(self,*,deadline=float('inf')):
        model=self.model
        low=max(-20.,float(self.context.bank.nodes_s[0]-self.obs.times_s.min())+1e-6)
        high=min(20.,float(self.context.bank.nodes_s[-1]-self.obs.times_s.max())-1e-6)
        nodes=np.arange(np.ceil(low*2)/2,high+1e-8,.5)
        best=np.full(len(self.tau),self.initial_objective)
        times=self.tau.copy()
        for value in nodes:
            if time.monotonic()>=deadline:
                break
            candidate=np.full(len(times),value)
            score=self.score(candidate)
            take=score<best
            best[take]=score[take]
            times[take]=candidate[take]
        centers=times.copy()
        # Refine the exact profile around each candidate's own best coarse mode.
        for step in np.arange(-.45,.45001,.05):
            if time.monotonic()>=deadline:
                break
            candidate=np.clip(centers+step,low,high)
            score=self.score(candidate)
            take=score<best
            best[take]=score[take]
            times[take]=candidate[take]
        order=np.argsort(best,kind='stable')
        proposals=[dict(index=int(k),satellite=int(model.bank.numbers[k]),timing_s=float(times[k]),
                       objective=float(best[k]),gain=float(self.initial_objective-best[k]))
                   for k in order if best[k]<self.initial_objective-1 and abs(times[k]-self.tau[k])>.05]
        return proposals


class BudgetExpired(Exception):
    pass


def fit(context,*,max_evaluations=1000,max_seconds=120):
    from common import refit
    begun=time.monotonic()
    deadline=min(begun+max_seconds,getattr(context,'deadline',float('inf')))
    v,n=context.vector.copy(),context.nuisance.copy()
    count=0
    projections=0
    rounds=[]
    current=float('inf')
    for iteration in range(2):
        if count>=max_evaluations*.45 or time.monotonic()>=begun+max_seconds*.55:
            break
        profile=Profiles(context,v,n)
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
            vv=timing_vector(context.model,v,tau)
            if abs(vv[7])>10:
                continue
            tail_start=context.model.base_nuisance_count
            limits=context.model.group_limits[context.model.original.group_count:]
            best=[float('inf'),n.copy()]
            local=0
            allowance=min(22,max_evaluations-count)
            def objective(tail):
                nonlocal count,local
                if local>=allowance or time.monotonic()>=deadline:
                    raise BudgetExpired()
                nn=n.copy()
                nn[tail_start:]=tail
                e=context.model.evaluate_joint(vv,nn)
                count+=1
                local+=1
                if e[0]<best[0]:
                    best[:]=[float(e[0]),nn.copy()]
                return e[0],e[2][tail_start:]
            try:
                if len(limits):
                    minimize(objective,n[tail_start:],jac=True,method='L-BFGS-B',
                        bounds=list(zip(-limits,limits)),options={'maxiter':20,'maxfun':allowance,'ftol':1e-10})
                else:
                    objective(np.empty(0))
            except BudgetExpired:
                pass
            accepted=best[0]<current-1e-7
            trials.append(dict(proposal=proposal,exact_objective=best[0] if np.isfinite(best[0]) else None,
                               accepted=accepted,evaluations=local))
            if accepted:
                v,n,current=vv,best[1],best[0]
        rounds.append(dict(initial_objective=profile.initial_objective,profile_proposals=proposals,trials=trials))
    remaining=max_evaluations-count
    polish={}
    if remaining>0 and time.monotonic()<deadline:
        solved=refit(context,v,n,max_evaluations=remaining,
                     max_seconds=max(.01,deadline-time.monotonic()),fixed_c=context.fixed_c)
        polish=solved['diagnostics']
        count+=polish['evaluations']
        if polish['objective']<=current+1e-7:
            v,n=solved['vector'],solved['nuisance']
            current=polish['objective']
    return dict(vector=v,nuisance=n,diagnostics=dict(method='exact-signed-all-point-timing-profiles',
                evaluations=count,orbit_projection_calls=projections,rounds=rounds,
                objective=current,polish=polish,elapsed_seconds=time.monotonic()-begun,
                qualification='Fixed-bank physical model and original classification. Profile columns are independent single-satellite exact objective changes.'))
