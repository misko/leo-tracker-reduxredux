"""Equivalent low-rank Gaussian prediction for long held satellite families."""

import numpy as np
from ds23_family_predictive_selection import gaussian_predictive


def fast_gaussian_predictive(raw,test_design,training_design,weights,prior_precision,noise_sigma):
    y,u,a,w,v,s=map(lambda z:np.asarray(z,float),(raw,test_design,training_design,weights,prior_precision,noise_sigma))
    if len(y)<=u.shape[1]:return gaussian_predictive(y,u,a,w,v,s)
    if (y.ndim!=1 or u.ndim!=2 or len(u)!=len(y) or a.ndim!=2 or a.shape[1]!=u.shape[1]
        or w.shape!=(len(a),) or v.shape!=(u.shape[1],) or s.shape!=y.shape
        or not all(np.isfinite(z).all() for z in (y,u,a,w,v,s)) or np.any(w<=0) or np.any(s<=0) or np.any(v<0)):
        raise ValueError('finite matching predictive arrays and valid precisions required')
    gram=np.diag(v)+a.T@(a*w[:,None]);root=np.linalg.cholesky((gram+gram.T)/2)
    projected=np.linalg.solve(root,u.T);features=projected/s[None,:];r=y/s
    normal=np.eye(len(gram))+features@features.T;chol=np.linalg.cholesky((normal+normal.T)/2)
    rhs=features@r;coefficient=np.linalg.solve(chol.T,np.linalg.solve(chol,rhs))
    residual=r-features.T@coefficient;quadratic=float(residual@residual+coefficient@coefficient)
    volume=2*np.log(s).sum()+2*np.log(np.diag(chol)).sum()
    return dict(negative_twice_log_density=float(quadratic+volume+len(y)*np.log(2*np.pi)),
        quadratic=quadratic,RMS_hz=float(np.sqrt(np.mean(y*y))),
        marginal_sigma_hz=np.sqrt(s*s+np.sum(projected**2,axis=0)),position_covariance_included=True)
