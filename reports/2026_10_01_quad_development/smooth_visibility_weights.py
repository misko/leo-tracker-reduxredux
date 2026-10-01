"""Experimental association weights; not integrated into any benchmark fitter."""
import numpy as np


def log_weights(margins_deg, margin_jacobian, width_deg, signal_mass):
    """Smooth an all-observations visibility gate and conserve association mass.

    Product of logistic gates is a modeling choice, not a measured probability.
    Jacobian has candidate, observation, parameter axes. Background absorbs
    the complement of visible signal mass, with its derivative included.
    """
    margins=np.asarray(margins_deg,dtype=float);jac=np.asarray(margin_jacobian,dtype=float)
    if margins.ndim!=2 or min(margins.shape)==0 or jac.ndim!=3 or jac.shape[:2]!=margins.shape:
        raise ValueError('nonempty aligned candidate/observation arrays required')
    if not np.all(np.isfinite(margins)) or not np.all(np.isfinite(jac)):
        raise ValueError('finite geometry required')
    if not np.isfinite(width_deg) or width_deg<=0 or not 0<signal_mass<1:
        raise ValueError('positive width and signal mass strictly between zero and one required')
    z=margins/width_deg
    log_gate=-np.logaddexp(0.,-z)
    complement=np.exp(-np.logaddexp(0.,z))
    log_visible=log_gate.sum(axis=1)
    dlog_visible=np.einsum('nt,ntd->nd',complement,jac)/width_deg
    visible=np.exp(log_visible)
    count=len(margins);coefficient=signal_mass/count
    background=1.-coefficient*visible.sum()
    background_gradient=-coefficient*np.einsum('n,nd->d',visible,dlog_visible)/background
    return (np.r_[np.log(coefficient)+log_visible,np.log(background)],
            np.vstack([dlog_visible,background_gradient]))
