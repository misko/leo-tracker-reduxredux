"""Track-level random horizon threshold, with explicit nondifferentiable ties."""
import numpy as np
from smooth_visibility_weights import log_weights


def shared_log_weights(margins_deg,margin_jacobian,width_deg,signal_mass):
    margins=np.asarray(margins_deg,dtype=float);jac=np.asarray(margin_jacobian,dtype=float)
    if margins.ndim!=2 or min(margins.shape)==0 or jac.ndim!=3 or jac.shape[:2]!=margins.shape:
        raise ValueError('nonempty aligned candidate/observation arrays required')
    if not np.all(np.isfinite(margins)) or not np.all(np.isfinite(jac)):
        raise ValueError('finite geometry required')
    indices=np.argmin(margins,axis=1);rows=np.arange(len(margins))
    minimum=margins[rows,indices];chosen=jac[rows,indices]
    tied=margins==minimum[:,None]
    # Exact ties with different first derivatives have no ordinary Jacobian.
    smooth=np.array([np.all(jac[i,tied[i]]==chosen[i]) for i in rows])
    logs,gradient=log_weights(minimum[:,None],chosen[:,None,:],width_deg,signal_mass)
    return logs,gradient if np.all(smooth) else None,dict(
        minimum_indices=indices,tie_counts=tied.sum(axis=1),differentiable=smooth)
