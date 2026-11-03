"""Whole-family predictive checks; held CFOs never set calibration or position."""

import numpy as np


def family_folds(labels,keep,maximum=2,minimum_points=24):
    labels,keep=np.asarray(labels),np.asarray(keep,bool)
    if labels.ndim!=1 or labels.shape!=keep.shape or maximum<1:
        raise ValueError('matching point labels and calibration mask required')
    groups=np.unique(labels[keep])
    if len(groups)<4:return []
    offered=sorted(((int(np.sum(keep&(labels==j))),int(j)) for j in groups),key=lambda r:(-r[0],r[1]))
    return [dict(family=j,train=keep&(labels!=j),test=keep&(labels==j))
            for count,j in offered[:maximum] if count>=minimum_points]


def gaussian_predictive(raw,test_design,training_design,weights,prior_precision,noise_sigma):
    """Exact Gaussian prediction with an improper flat local position prior.

    The caller supplies mean residuals from a training-only fit. The first two
    design coordinates are position; remaining coordinates have proper priors.
    Held-family Student phase uses its prior marginal variance, not an
    underdispersed unobserved variational precision.
    """
    y,u,a,w,v,s=map(lambda z:np.asarray(z,float),
        (raw,test_design,training_design,weights,prior_precision,noise_sigma))
    if (y.ndim!=1 or u.ndim!=2 or len(u)!=len(y) or a.ndim!=2 or a.shape[1]!=u.shape[1]
            or w.shape!=(len(a),) or v.shape!=(u.shape[1],) or s.shape!=y.shape
            or not all(np.isfinite(z).all() for z in (y,u,a,w,v,s))
            or np.any(w<=0) or np.any(s<=0) or np.any(v<0)):
        raise ValueError('finite matching prediction arrays and valid precisions required')
    gram=np.diag(v)+a.T@(a*w[:,None])
    root=np.linalg.cholesky((gram+gram.T)/2)
    projected=np.linalg.solve(root,u.T)
    covariance=np.diag(s*s)+projected.T@projected
    chol=np.linalg.cholesky((covariance+covariance.T)/2)
    white=np.linalg.solve(chol,y)
    return dict(negative_twice_log_density=float(white@white+2*np.log(np.diag(chol)).sum()+len(y)*np.log(2*np.pi)),
        quadratic=float(white@white),RMS_hz=float(np.sqrt(np.mean(y*y))),
        marginal_sigma_hz=np.sqrt(np.diag(covariance)),position_covariance_included=True)


def qualified_gain(rows,penalty=2*np.log(2)):
    if len(rows)!=2:return False
    return bool(all(r['qualified_training'] for r in rows) and
                min(r['gain'] for r in rows)>0 and sum(r['gain'] for r in rows)>penalty)
