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
