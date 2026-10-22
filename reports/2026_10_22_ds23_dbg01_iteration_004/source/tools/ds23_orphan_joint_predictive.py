"""Carry covariance between existing linear evidence and new orphan points.

This is Gaussian integral factorization only. The published curved calibration
coefficients and their normal equations are never replaced by linear estimates.
"""

import numpy as np

from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from ds23_orphan_adaptive_importance import AdaptiveOrphans


def condition_gaussian(design,residual,variance,groups,bias_sigma=300.):
    """Posterior of unit-normal latent coordinates under grouped predictions."""
    a,y,v,g=map(np.asarray,[design,residual,variance,groups])
    inverse_a=a/v[:,None];inverse_y=y/v
    covariance=np.diag(v)
    for group in np.unique(g):
        use=g==group;one=1/v[use];denominator=1/bias_sigma**2+one.sum()
        inverse_a[use]-=one[:,None]*(inverse_a[use].sum(axis=0)/denominator)
        inverse_y[use]-=one*(inverse_y[use].sum()/denominator)
        covariance[np.ix_(use,use)]+=bias_sigma**2
    precision=np.eye(a.shape[1])+a.T@inverse_a
    mean=np.linalg.solve(precision,a.T@inverse_y);posterior=np.linalg.inv(precision)
    total=covariance+a@a.T
    score=float(y@np.linalg.solve(total,y)+np.linalg.slogdet(total)[1]+len(y)*np.log(2*np.pi))
    return mean,posterior,score


class JointPredictiveOrphans(AdaptiveOrphans):
    def __init__(self,prediction,x,entries):
        super().__init__(prediction,x);p=prediction.p
        self.old_linear_density_difference=0.
        if not entries:return
        c=p.curved_calculate(x)
        u=c['features'][p.keep];g=p.noise_groups[p.keep]
        weights=prediction.powers[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:,None]);covariance=np.linalg.inv(gram)
        root=np.linalg.cholesky((covariance+covariance.T)/2)
        view,values,sigma,groups,_=linear_geometry(p,entries);geometry=geometry_features(view,x,0.)
        residual=values-view.q*geometry['intercept']-geometry['features']@c['coefficient']
        design=geometry['features']@root
        mean,posterior,score=condition_gaussian(design,residual,2*sigma*sigma,groups)
        self.old_linear_density_difference=abs(score-p.calculate(x)['linear_predictive_objective'])
        if self.old_linear_density_difference>1e-5:raise ValueError('original linear integral fails independent dense replay')
        width=prediction.width
        self.base+=self.design[:,:width]@mean
        self.design[:,:width]=self.design[:,:width]@np.linalg.cholesky((posterior+posterior.T)/2)
