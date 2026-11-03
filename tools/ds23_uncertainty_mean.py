"""Positive Gaussian quadrature and local nuisance-projected mean diagnostics."""

import itertools
import numpy as np


def gaussian_nodes(mean,covariance,rule='spherical'):
    mu,c=np.asarray(mean,float),np.asarray(covariance,float)
    if mu.ndim!=1 or not len(mu) or c.shape!=(len(mu),len(mu)) or not np.isfinite(mu).all() or not np.isfinite(c).all():
        raise ValueError('finite mean and matching positive Gaussian covariance required')
    root=np.linalg.cholesky(c);d=len(mu)
    if rule=='spherical':
        z=np.r_[np.sqrt(d)*np.eye(d),-np.sqrt(d)*np.eye(d)];weight=np.full(2*d,1/(2*d))
    elif rule=='hermite3':
        knot,w=np.polynomial.hermite.hermgauss(3);indices=np.array(list(itertools.product(range(3),repeat=d)))
        z=np.sqrt(2)*knot[indices];weight=np.prod(w[indices]/np.sqrt(np.pi),axis=1)
    else:raise ValueError('unknown positive Gaussian quadrature')
    return mu+z@root.T,weight


def projected_mean_shift(position_derivative,features,weight,prior_precision,mean_shift):
    """First-order fit displacement; Gamma/identities fixed, not a new estimate."""
    j,u,w,v,b=map(np.asarray,(position_derivative,features,weight,prior_precision,mean_shift))
    if j.shape!=(len(w),2) or u.shape[0]!=len(w) or v.shape!=(u.shape[1],) or b.shape!=(len(w),) or np.any(w<=0) or np.any(v<=0):
        raise ValueError('matching position derivatives, nuisances, positive weights and shift required')
    root=np.sqrt(w);a=np.vstack((u*root[:,None],np.diag(np.sqrt(v))))
    q,_=np.linalg.qr(a,mode='reduced');d=np.vstack((j*root[:,None],np.zeros((len(v),2))))
    y=np.r_[b*root,np.zeros(len(v))];d-=q@(q.T@d);y-=q@(q.T@y)
    information=d.T@d;delta=-np.linalg.solve(information,d.T@y)
    return dict(predicted_position_shift_km=delta,predicted_shift_norm_km=float(np.linalg.norm(delta)),
        nuisance_projected_shift_weighted_norm=float(np.linalg.norm(y)),
        local_information=information,conditioned_on_Gamma_labels_and_linearization=True,
        not_marginal_evidence_gradient_or_regional_position_estimate=True)
