"""Exact one-candidate replacements in the existing selected-CFO likelihood."""
import numpy as np
from leo.analysis.regional_position_score import observer,LIGHT_KM_S


def components(measured,prediction,visibility,sigma,q,alias_hz):
    p=visibility*q
    odds=p/(1-p)
    residual=(measured-prediction+alias_hz/2)%alias_hz-alias_hz/2
    gaussian=np.exp(-.5*(residual/sigma)**2)/(sigma*np.sqrt(2*np.pi))
    return odds,odds*gaussian


def replacement_nll(other_odds,other_signal,odds,signal,clutter_rate,alias_hz):
    """Rows can be broadcasting timing batches; others exclude this candidate."""
    normalizer=clutter_rate+other_odds+odds
    total=clutter_rate/alias_hz+other_signal+signal
    return np.sum(np.log(normalizer)-np.log(total),axis=-1)


def timing_penalty(total,common_sigma,relative_sigma):
    total=np.asarray(total);mean=total.mean(axis=-1)
    return .5*(mean/common_sigma)**2+.5*np.sum(((total-mean[...,None])/relative_sigma)**2,axis=-1)


def replaced_timing_penalty(total,index,proposed,common_sigma,relative_sigma):
    """Prior for one changed timing, preserving the common/zero-sum gauge."""
    total=np.asarray(total,float);proposed=np.asarray(proposed,float)
    k=len(total);sums=total.sum()-total[index]+proposed
    squares=np.sum(total*total)-total[index]**2+proposed**2
    means=sums/k
    return .5*(means/common_sigma)**2+.5*(squares-k*means**2)/relative_sigma**2


def predict_single_candidate(bank,observations,prior,point,timings):
    """Batch the original linear state interpolator for exactly one candidate.

    Only orbital query time moves. Receive-time calibration is deliberately
    outside this function and remains evaluated at the original observations.
    """
    timings=np.asarray(timings,float)
    if len(bank.numbers)!=1 or timings.ndim!=1 or not np.isfinite(timings).all():
        raise ValueError('One candidate and finite timing vector required')
    query=timings[:,None]+observations.times_s[None,:]
    if query.min()<bank.nodes_s[0] or query.max()>bank.nodes_s[-1]:
        raise ValueError('Orbit query outside declared ephemeris support')
    fraction=(query-bank.nodes_s[0])/(bank.nodes_s[1]-bank.nodes_s[0])
    lower=np.minimum(np.floor(fraction).astype(int),len(bank.nodes_s)-2)
    w=(fraction-lower)[...,None]
    p0=bank.position_km[0,lower];p1=bank.position_km[0,lower+1]
    v0=bank.velocity_km_s[0,lower];v1=bank.velocity_km_s[0,lower+1]
    position=p0+w*(p1-p0);velocity=v0+w*(v1-v0)
    site,up=observer(prior,point);delta=position-site
    distance=np.linalg.norm(delta,axis=2)
    if np.any(distance<=0):raise ValueError('Candidate coincides with observer')
    direction=delta/distance[...,None]
    prediction=-(observations.rf_hz[None,:]/LIGHT_KM_S)*np.sum(direction*velocity,axis=2)
    sine=np.einsum('bni,i->bn',direction,up)
    return prediction,sine
