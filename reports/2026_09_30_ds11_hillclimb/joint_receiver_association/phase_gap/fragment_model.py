"""Diagnostic clock fit with externally fixed fitting/evaluation masks."""
import numpy as np
from scipy.optimize import least_squares
from model import wrap


def predict(t,phase,training,held,period):
    t,phase=np.asarray(t,float),np.asarray(phase,float)
    training,held=np.asarray(training,bool),np.asarray(held,bool)
    if t.ndim!=1 or any(a.shape!=t.shape for a in (phase,training,held)):
        raise ValueError('shape mismatch')
    if np.any(training & held):raise ValueError('overlapping masks')
    if training.sum()<6 or len(np.unique(t[training]))<3 or held.sum()==0:
        return dict(qualified=False,reason='insufficient_support')
    center=float(t[training].mean());scale=float(np.ptp(t[training]))
    u=(t-center)/scale;x=np.column_stack((np.ones(len(t)),u,u*u))
    order=np.argsort(t[training],kind='stable')
    design=x[training][order];y=np.unwrap(phase[training][order],period=period)
    initial=np.linalg.lstsq(design,y,rcond=None)[0]
    fit=least_squares(lambda b:design@b-y,initial,jac=lambda b:design,
                      loss='soft_l1',f_scale=.1,max_nfev=300,
                      ftol=1e-12,xtol=1e-12,gtol=1e-10)
    return dict(qualified=bool(fit.success and fit.optimality<1e-4),
                coefficients=fit.x.tolist(),center_s=center,scale_s=scale,
                errors_us=wrap(phase[held]-x[held]@fit.x,period).tolist())
