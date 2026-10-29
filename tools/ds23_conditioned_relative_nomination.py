"""Gaussian-predictive nominations with correlated, externally fitted priors.

The GLRT posterior and moment-matched unseen phase priors are frozen inputs.
These are finite-pool proposal scores, not calibrated emitter probabilities.
Final localization must restore the original hierarchical physical priors.
"""

import numpy as np
from ds23_frozen_precision import conditional_gaussian
from leo.analysis.research.retained_track_likelihood import PERIOD


def gaussian_prediction(raw,design,covariance,sigma):
    y,u,c=np.asarray(raw,float),np.asarray(design,float),np.asarray(covariance,float)
    if u.shape[0]!=len(y) or c.shape!=(u.shape[1],u.shape[1]):raise ValueError('matching prediction modes and covariance required')
    root=np.linalg.cholesky(c);noise=np.broadcast_to(np.asarray(sigma,float),y.shape)
    result=conditional_gaussian(y,u@root,noise,np.ones(len(y)),np.ones(len(y)),np.ones(u.shape[1]),1.)
    result['parameter_update']=root@result['coefficient']
    result['native_residual']=y-u@result['parameter_update']
    return result


def refine_prediction(values,geometry,mean,covariance,phase_scale,sigma,*,rounds=5):
    """Relinearize phases while preserving the same absolute prior and covariance."""
    y,mu,c,sd=map(np.asarray,(values,mean,covariance,phase_scale));reference=mu[:2]*sd
    history=[]
    for _ in range(rounds):
        g=geometry(reference);result=gaussian_prediction(y-g['intercept']-g['features']@mu,g['features'],c,sigma)
        coefficient=mu+result['parameter_update'];phase=coefficient[:2]*sd
        change=float(np.max(abs(phase-reference)));history.append(change);reference=np.clip(phase,-15,15)
    phase=coefficient[:2]*sd
    if np.max(abs(phase))<=15:
        exact=geometry(phase);residual=y-exact['intercept']-exact['features']@coefficient;elevation=exact['elevation']
    else:residual=result['native_residual'];elevation=np.full(len(y),-90.)
    return dict(score=result['objective'],coefficient=coefficient,phase_s=phase,residual_hz=residual,
        RMS_hz=float(np.sqrt(np.mean(residual**2))),minimum_elevation_deg=float(elevation.min()),
        phase_change_s=change,phase_valid=bool(np.max(abs(phase))<=15),history=history,
        approximate_Gaussian_predictive_score_not_identity_probability=True)


def unresolved_curve_score(times,values,sigma):
    """Proper broad degree4 Legendre prior for a position-independent null curve."""
    t,y=np.asarray(times,float),np.asarray(values,float)
    if np.ptp(t)<=0:raise ValueError('nonzero time span required')
    z=2*(t-t.min())/np.ptp(t)-1
    design=np.polynomial.legendre.legvander(z,4)*PERIOD/np.sqrt(6)
    return gaussian_prediction(y,design,np.eye(5),sigma)['objective']
