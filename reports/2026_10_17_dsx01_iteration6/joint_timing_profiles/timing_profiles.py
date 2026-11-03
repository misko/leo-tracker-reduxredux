"""Exact one-candidate timing profiles from complete current-model residuals.

This array port never reconstructs a calibration function. A caller supplies the
current wrapped residuals and orbital predictions; changes in orbital prediction
then transport that residual while every band/clock/RF correction stays fixed.
No optimizer or proposal-selection policy is implemented here.
"""
from __future__ import annotations
import numpy as np
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ,circular
from leo.analysis.shared_scan_model import elevation_geometry,horizon_weight


def timing_vector(vector,basis,times):
    """Recenter total candidate times into the unchanged common/zero-sum gauge."""
    v=np.asarray(vector,float).copy();times=np.asarray(times,float)
    basis=np.asarray(basis,float)
    if times.ndim!=1 or basis.shape!=(len(times),len(times)-1) or len(v)!=len(times)+7:
        raise ValueError('Aligned physical vector, total timings and zero-sum basis required')
    if not np.isfinite(times).all():raise ValueError('Finite candidate timings required')
    v[7]=times.mean();v[8:]=basis.T@(times-v[7])
    return v


def timing_penalty_delta(tau,proposed,common_sigma=3.,relative_sigma=2.):
    """Each output changes only its own candidate, including all recentered priors."""
    tau,proposed=np.asarray(tau,float),np.asarray(proposed,float)
    if tau.ndim!=1 or proposed.shape!=tau.shape or not np.isfinite(np.r_[tau,proposed]).all():
        raise ValueError('Aligned finite candidate timings required')
    if common_sigma!=3. or relative_sigma!=2.:
        raise ValueError('This adapter is qualified only for unchanged3s/2s priors')
    delta=proposed-tau;k=len(tau);common=tau.mean()
    return (.5*((common+delta/k)**2-common**2)/common_sigma**2
        +(delta*(tau-common)+.5*delta**2*(1-1/k))/relative_sigma**2)


def _readonly(value):
    out=np.array(value,float,copy=True);out.flags.writeable=False;return out


class ResidualProfiles:
    """K independent single-coordinate objectives per paired orbit projection.

    ``project(times)`` returns (orbital_prediction_hz, visibility_weight), both
    N-by-K and evaluated at the actual observation RF/support times. The public
    array interface also supports ``score_projected`` without any model object.
    All non-timing penalties are carried in ``initial_objective`` exactly once.
    """
    def __init__(self,*,residual_hz,orbital_prediction_hz,visibility_weight,
                 sigma_hz,q,tau,score,initial_objective,project=None):
        residual,orbit,weight=map(np.asarray,(residual_hz,orbital_prediction_hz,visibility_weight))
        sigma,q,tau=map(np.asarray,(sigma_hz,q,tau))
        if (residual.ndim!=2 or orbit.shape!=residual.shape or weight.shape!=residual.shape
            or sigma.shape!=(len(residual),) or q.shape!=(residual.shape[1],) or tau.shape!=q.shape
            or not len(q) or any(not np.isfinite(a).all() for a in [residual,orbit,weight,sigma,q,tau])
            or np.any((weight<0)|(weight>1)) or np.any((q<=0)|(q>=1))
            or np.any((sigma<=0)|(sigma>1000)) or abs(q.sum()-score.detection_budget)>1e-10
            or not np.isfinite(initial_objective) or score.common_sigma_s!=3. or score.relative_sigma_s!=2.):
            raise ValueError('Original aligned shared-q arrays, full budget and3s/2s priors required')
        self.residual_hz=_readonly(residual);self.orbital_prediction_hz=_readonly(orbit)
        self.visibility_weight=_readonly(weight);self.sigma_hz=_readonly(sigma)
        self.q=_readonly(q);self.tau=_readonly(tau);self.score_config=score
        self.initial_objective=float(initial_objective);self.project=project
        odds=weight*q[None,:]/(1-weight*q[None,:])
        gaussian=np.exp(-.5*(residual/sigma[:,None])**2)/(sigma[:,None]*np.sqrt(2*np.pi))
        signal=odds*gaussian
        self.clutter_density=score.clutter_rate/ALIAS_HZ
        total=self.clutter_density+signal.sum(1);normalizer=score.clutter_rate+odds.sum(1)
        self.initial_nll=float(np.sum(np.log(normalizer)-np.log(total)))
        self.fixed_penalty=self.initial_objective-self.initial_nll
        self.remaining_total=np.maximum(total[:,None]-signal,self.clutter_density)
        self.remaining_normalizer=np.maximum(normalizer[:,None]-odds,score.clutter_rate)
        self.projection_calls=0;self.coordinate_comparisons=0

    def score_projected(self,times,orbital_prediction_hz,visibility_weight):
        times=np.asarray(times,float);pred=np.asarray(orbital_prediction_hz,float);weight=np.asarray(visibility_weight,float)
        if (times.shape!=self.tau.shape or pred.shape!=self.residual_hz.shape or weight.shape!=pred.shape
            or any(not np.isfinite(a).all() for a in [times,pred,weight]) or np.any((weight<0)|(weight>1))):
            raise ValueError('Aligned finite proposed timings, orbital predictions and visibility required')
        # Subtract orbital predictions before adding to avoid needless loss of
        # residual precision. The complete learned calibration remains implicit.
        residual=circular(self.residual_hz+(self.orbital_prediction_hz-pred))
        odds=weight*self.q[None,:]/(1-weight*self.q[None,:])
        gaussian=np.exp(-.5*(residual/self.sigma_hz[:,None])**2)/(self.sigma_hz[:,None]*np.sqrt(2*np.pi))
        nll=np.sum(np.log(self.remaining_normalizer+odds)-np.log(self.remaining_total+odds*gaussian),axis=0)
        self.coordinate_comparisons+=len(times)
        return nll+self.fixed_penalty+timing_penalty_delta(self.tau,times,
            self.score_config.common_sigma_s,self.score_config.relative_sigma_s)

    def score(self,times):
        if self.project is None:raise ValueError('An explicit orbit projection port is required')
        prediction,weight=self.project(np.asarray(times,float))
        self.projection_calls+=1
        return self.score_projected(times,prediction,weight)


def from_context(context,vector,nuisance):
    """Narrow scientific adapter: evaluate current model once, never decode bands.

    The context/model contract is the existing public analysis port. Calibration
    details, concrete storage and measured values outside scored observations are
    neither inspected nor reconstructed.
    """
    model=context.model;v=np.array(vector,float,copy=True);n=np.array(nuisance,float,copy=True)
    observations=model.scored_observations;tau=v[7]+model.basis@v[8:]
    result,details=model.evaluate_details(v,n)
    def project(times):
        prediction=predict_orbits(context.bank,observations,context.prior,v[:2],times,derivatives=False)[0]
        sine=elevation_geometry(context.bank,observations,context.prior,v[:2],times)[0]
        return prediction,horizon_weight(sine,model.visibility_width)[0]
    orbital=project(tau)[0]
    profile=ResidualProfiles(residual_hz=result[3].residual_hz,orbital_prediction_hz=orbital,
        visibility_weight=details['visibility_weight'],sigma_hz=details['sigma_hz'],
        q=details['detection_probability'],tau=tau,score=model.score,initial_objective=result[0],project=project)
    np.testing.assert_allclose(profile.initial_nll,result[3].nll,atol=1e-9,rtol=0)
    profile.construction_objective_calls=1;profile.construction_projection_calls=1
    return profile
