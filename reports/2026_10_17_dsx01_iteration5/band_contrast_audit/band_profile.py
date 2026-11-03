"""Bounded separable TRAIN-only profiles of two frozen high-band offsets."""
from dataclasses import dataclass
import time
import numpy as np
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.analysis.shared_scan_model import SharedScanObjective,density


@dataclass(frozen=True)
class Grid:
    coarse_radius_hz: int=10000
    coarse_step_hz: int=500
    fine_radius_hz: int=500
    fine_step_hz: int=25
    max_evaluations: int=200
    max_seconds: float=120.


class Exhausted(Exception):pass


class BandProfiles:
    def __init__(self,context,vector,nuisance,grid=Grid()):
        if type(context.model) is not SharedScanObjective:raise ValueError('Original frozen-contrast shared objective required')
        self.model=context.model;self.grid=grid;self.begun=time.monotonic()
        self.calls=0;self.full_objective_calls=0;self.density_calls=0;self.cache_hits=0;self.requests=0
        self.v=np.asarray(vector,float).copy();self.n=np.asarray(nuisance,float).copy()
        self.v.setflags(write=False);self.n.setflags(write=False)
        self.obs=self.model.scored_observations;raw=self.model.original
        self.receivers=tuple(map(int,np.unique(self.obs.receiver[self.obs.channel>=5])))
        if self.receivers!=(0,1):raise ValueError('Both receiver high-band lanes must have training support')
        self.current=np.array([raw.baseline[(raw.observations.receiver==r)&(raw.observations.channel>=5)][0] for r in self.receivers])
        expected=sum((raw.observations.receiver==r)*(raw.observations.channel>=5)*offset for r,offset in zip(self.receivers,self.current))
        np.testing.assert_allclose(expected,raw.baseline,atol=1e-10,rtol=0)
        self._allow();self.calls+=1;self.full_objective_calls+=1
        ev,details=self.model.evaluate_details(self.v,self.n)
        self.original_objective=float(ev[0]);self.original_nll=float(ev[3].nll)
        self.original_row_nll=details['row_nll'].copy();self.visibility=details['visibility_weight'].copy()
        self.q=details['detection_probability'].copy();self.sigma=details['sigma_hz'].copy()
        clock,group=raw.split(self.n[:self.model.base_nuisance_count]);mask=self.model.mask
        tau=self.v[7]+self.model.basis@self.v[8:]
        prediction=predict_orbits(self.model.bank,self.obs,self.model.prior,self.v[:2],tau)[0]
        baseline=raw.baseline+raw.group_design@group
        correction=raw.design[mask]@self.v[2:7]+baseline[mask]+raw.clock_design[mask]@clock
        self.prediction=prediction+correction[:,None]
        self.lanes=[np.flatnonzero((self.obs.receiver==r)&(self.obs.channel>=5)) for r in self.receivers]
        self.base_lane_nll=np.array([self.original_row_nll[rows].sum() for rows in self.lanes])
        self.cache=[{0.:float(value)} for value in self.base_lane_nll]
        zero=self._density(np.arange(len(self.obs.times_s)),0.)
        np.testing.assert_allclose(zero.nll,self.original_nll,atol=1e-9,rtol=0)
        self.fixed_prior=.5*float(self.current@self.current)/50000.**2
        np.testing.assert_allclose(self.fixed_prior,self.model.fixed_contrast_prior_penalty,atol=1e-12,rtol=0)

    def _allow(self,reserve=0):
        if self.calls>=self.grid.max_evaluations-reserve or time.monotonic()-self.begun>=self.grid.max_seconds:raise Exhausted()

    def _density(self,rows,update,*,reserve=0):
        self._allow(reserve);self.calls+=1;self.density_calls+=1
        return density(self.obs.measured_hz[rows],self.prediction[rows]+update,self.visibility[rows],
            self.sigma[rows],self.q,self.model.score)[0]

    def lane(self,index,update):
        self.requests+=1;update=float(update)
        if abs(self.current[index]+update)>ALIAS_HZ/2+1e-7:raise ValueError('Physical contrast outside original alias-branch bounds')
        if update in self.cache[index]:self.cache_hits+=1
        else:self.cache[index][update]=float(self._density(self.lanes[index],update,reserve=1).nll)
        # Absolute offset prior referenced to zero, not a prior on the update.
        return self.cache[index][update]+.5*((self.current[index]+update)/50000.)**2

    def objective(self,updates):
        updates=np.asarray(updates,float)
        if updates.shape!=(2,):raise ValueError('Two receiver contrast updates required')
        if np.all(updates==0):return self.original_objective
        change=sum(self.cache[i][float(update)]-self.base_lane_nll[i] for i,update in enumerate(updates))
        prior_delta=.5*float((self.current+updates)@(self.current+updates)-self.current@self.current)/50000.**2
        return self.original_objective+float(change)+prior_delta

    def fit(self):
        updates=np.zeros(2);trace=[];reason='grid-complete'
        try:
            for index,receiver in enumerate(self.receivers):
                best=(self.lane(index,0.),0.)
                coarse=np.arange(-self.grid.coarse_radius_hz,self.grid.coarse_radius_hz+1,self.grid.coarse_step_hz,dtype=float)
                for update in coarse:
                    if abs(self.current[index]+update)>ALIAS_HZ/2:continue
                    value=self.lane(index,update);trace.append(dict(receiver=receiver,phase='coarse',update_hz=float(update),lane_objective=value))
                    if (value,abs(update),update)<(best[0],abs(best[1]),best[1]):best=(value,float(update))
                    updates[index]=best[1]
                center=best[1]
                fine=center+np.arange(-self.grid.fine_radius_hz,self.grid.fine_radius_hz+1,self.grid.fine_step_hz,dtype=float)
                # Refinement stays within the same predeclared local physical search box.
                for update in fine:
                    if abs(update)>self.grid.coarse_radius_hz or abs(self.current[index]+update)>ALIAS_HZ/2:continue
                    value=self.lane(index,update);trace.append(dict(receiver=receiver,phase='fine',update_hz=float(update),lane_objective=value))
                    if (value,abs(update),update)<(best[0],abs(best[1]),best[1]):best=(value,float(update))
                    updates[index]=best[1]
        except Exhausted:reason='evaluation-or-wall-budget'
        objective=self.objective(updates)
        if objective>self.original_objective:updates[:]=0;objective=self.original_objective
        # One reserved full-density check of the separability/prior bookkeeping.
        verification=None
        try:
            self._allow();self.calls+=1;self.density_calls+=1
            shift=sum((self.obs.receiver==r)*(self.obs.channel>=5)*update for r,update in zip(self.receivers,updates))
            terms,_=density(self.obs.measured_hz,self.prediction+shift[:,None],self.visibility,self.sigma,self.q,self.model.score)
            expected=self.original_objective+(terms.nll-self.original_nll)+.5*float((self.current+updates)@(self.current+updates)-self.current@self.current)/50000.**2
            np.testing.assert_allclose(objective,expected,atol=1e-8,rtol=0)
            verification=float(expected)
        except Exhausted:reason='evaluation-or-wall-budget'
        return dict(updates_hz=updates,absolute_offsets_hz=self.current+updates,
            training_objective=objective,training_objective_before=self.original_objective,
            training_nll_before=self.original_nll,
            training_nll=self.original_nll+sum(self.cache[i][float(u)]-self.base_lane_nll[i] for i,u in enumerate(updates)),
            trace=trace,diagnostics=dict(evaluations=self.calls,full_shared_objective_calls=self.full_objective_calls,
                partial_or_full_density_calls=self.density_calls,profile_requests=self.requests,cache_hits=self.cache_hits,
                optimization_orbit_queries=2,elapsed_seconds=time.monotonic()-self.begun,
                full_density_endpoint_objective=verification,reason=reason,
                original_incumbent_retained=bool(np.all(updates==0)),continuous_kkt_claimed=False),
            prior_policy='J=originalJ+laneNLLdelta+.5*(sum(new_absolute_offsets**2)-sum(original_absolute_offsets**2))/50000**2; other priors once')
