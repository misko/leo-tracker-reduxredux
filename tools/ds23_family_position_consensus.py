"""Position-estimator diagnostics from whole-satellite deletion fits.

These are candidate estimators, not calibrated uncertainty or a proved bias
correction for heterogeneous satellite geometry. Every deletion fit must use
the same physical model and remove that family's curved AND predictive data.
Final candidates require full original-data gate and phase-refresh replays.
"""

import numpy as np


def geometric_median(points,tolerance=1e-9,iterations=1000):
    a=np.asarray(points,float)
    if a.ndim!=2 or a.shape[1]!=2 or not len(a) or not np.isfinite(a).all():
        raise ValueError('finite nonempty two-coordinate positions required')
    x=np.median(a,axis=0)
    for _ in range(iterations):
        distances=np.linalg.norm(a-x,axis=1);nonzero=distances>1e-12
        if not nonzero.any():return x
        w=1/distances[nonzero];proposal=(a[nonzero]*w[:,None]).sum(axis=0)/w.sum()
        zeros=int(np.sum(~nonzero))
        if zeros:
            residual=np.sum((a[nonzero]-x)/distances[nonzero,None],axis=0)
            norm=float(np.linalg.norm(residual))
            if norm<=zeros:return x
            ratio=zeros/norm;proposal=(1-ratio)*proposal+ratio*x
        if np.linalg.norm(proposal-x)<=tolerance:return proposal
        x=proposal
    raise ValueError('geometric median did not converge within declared budget')


def position_candidates(full_position,leave_one_family_out):
    full,deleted=np.asarray(full_position,float),np.asarray(leave_one_family_out,float)
    if (full.shape!=(2,) or deleted.ndim!=2 or deleted.shape[1]!=2 or len(deleted)<4
            or not np.isfinite(full).all() or not np.isfinite(deleted).all()):
        raise ValueError('finite full fit and at least four family-deletion positions required')
    g=len(deleted);mean=deleted.mean(axis=0);centered=deleted-mean
    return dict(mean=mean,geometric_median=geometric_median(deleted),
        jackknife=g*full-(g-1)*mean,
        jackknife_covariance_diagnostic=(g-1)/g*centered.T@centered,
        delete_group_count=g,uncertainty_not_calibrated=True)
