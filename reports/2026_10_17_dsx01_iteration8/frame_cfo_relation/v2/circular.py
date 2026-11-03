"""Exact global circular least-squares intercept; no unwrapped path selection."""
import numpy as np


def wrap(value,period):return (np.asarray(value)+period/2)%period-period/2


def intercept(values,period):
    values=np.asarray(values,float)
    if values.ndim!=1 or not len(values) or not np.isfinite(values).all() or not np.isfinite(period) or period<=0:
        raise ValueError('Nonempty finite values and positive finite period required')
    ordered=np.sort(values%period);candidates=[]
    for cut in range(len(ordered)):
        lifted=np.r_[ordered[cut:],ordered[:cut]+period]
        mean=float(wrap(lifted.mean(),period));sse=float(np.sum(wrap(values-mean,period)**2))
        candidates.append((sse,abs(mean),mean))
    best=min(candidates)
    return dict(offset=best[2],training_sse=best[0],enumerated_cuts=len(ordered))
