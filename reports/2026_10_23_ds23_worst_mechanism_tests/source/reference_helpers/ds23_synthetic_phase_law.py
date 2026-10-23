"""Unit-variance phase law matching the frozen Normal/Gamma nuisance prior."""

import numpy as np


def unit_variance_law(nu):
    from scipy.stats import norm,t
    if nu is None:return norm()
    if not np.isfinite(nu) or nu<=2:raise ValueError('Student prior degrees must exceed two')
    return t(float(nu),scale=float(np.sqrt((nu-2)/nu)))


def bounded_phase_draw(means,sigmas,nu,uniforms):
    means,sigmas,u=[np.asarray(x,float) for x in (means,sigmas,uniforms)]
    if means.shape!=sigmas.shape or means.shape!=u.shape or not all(np.isfinite(x).all() for x in (means,sigmas,u)):
        raise ValueError('matching finite phase coordinates required')
    if np.any(sigmas<=0) or np.any((u<=0)|(u>=1)):raise ValueError('positive scales and interior quantiles required')
    law=unit_variance_law(nu)
    lower=law.cdf((-15-means)/sigmas);upper=law.cdf((15-means)/sigmas)
    if np.any(upper<=lower):raise ValueError('phase prior has no representable mass in search domain')
    return means+sigmas*law.ppf(lower+u*(upper-lower))
