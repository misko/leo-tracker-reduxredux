"""Measure phase convergence before clipping the next linearization reference."""
import numpy as np


def phase_refresh(phases,reference,limit_s=15.):
    actual,old=np.asarray(phases,float),np.asarray(reference,float)
    if actual.shape!=old.shape or actual.ndim!=1 or not len(actual) or not np.isfinite(np.r_[actual,old,limit_s]).all() or limit_s<=0:
        raise ValueError('matching finite nonempty phase vectors and positive bound required')
    updated=np.clip(actual,-limit_s,limit_s)
    return updated,dict(phase_change_s=float(np.max(abs(actual-old))),
        clipped_reference_change_s=float(np.max(abs(updated-old))),
        phase_outside_reference_window=bool(np.any(abs(actual)>limit_s)),
        maximum_phase_overflow_s=float(np.max(np.maximum(abs(actual)-limit_s,0.))))


def reference_domain(knots,times,labels,phases,padding_s=.05):
    """Require phase geometry and its finite derivative to stay in the bank."""
    knots,times,labels,phases=map(np.asarray,(knots,times,labels,phases))
    if knots.ndim!=1 or len(knots)<2 or np.any(np.diff(knots)<=0) or times.ndim!=1 or labels.shape!=times.shape or not len(times):
        raise ValueError('ordered bank and matching nonempty observation geometry required')
    if phases.ndim!=1 or not np.issubdtype(labels.dtype,np.integer) or np.any(labels<0) or np.any(labels>=len(phases)):
        raise ValueError('valid phase labels required')
    if not np.isfinite(np.r_[knots,times,phases,padding_s]).all() or padding_s<0:raise ValueError('finite geometry and nonnegative padding required')
    requested=times+phases[labels];margin=float(min(requested.min()-padding_s-knots[0],knots[-1]-requested.max()-padding_s))
    return dict(bank_start_s=float(knots[0]),bank_end_s=float(knots[-1]),minimum_requested_s=float(requested.min()),
        maximum_requested_s=float(requested.max()),derivative_padding_s=padding_s,minimum_margin_s=margin,in_domain=margin>=0)
