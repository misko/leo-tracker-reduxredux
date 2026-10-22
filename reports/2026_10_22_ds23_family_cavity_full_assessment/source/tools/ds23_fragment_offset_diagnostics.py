"""Correlated descriptive summaries of posterior fragment offsets."""

import numpy as np


def contrast_summary(mean,covariance,first,second=(),weights=None):
    mu,cov=np.asarray(mean,float),np.asarray(covariance,float)
    if mu.ndim!=1 or cov.shape!=(len(mu),len(mu)):raise ValueError('matching fragment means and covariance required')
    w=np.zeros(len(mu));scale=np.ones(len(mu)) if weights is None else np.asarray(weights,float)
    for indices,sign in [(first,1.),(second,-1.)]:
        indices=np.asarray(indices,int)
        if len(indices):w[indices]+=sign*scale[indices]/scale[indices].sum()
    variance=float(w@cov@w)
    if variance< -1e-6:raise ValueError('nonnegative posterior contrast variance required')
    return dict(mean_hz=float(w@mu),conditional_SD_hz=float(np.sqrt(max(0,variance))),weights=w,
        posterior_summary_not_independent_measurement_or_hardware_identification=True)
