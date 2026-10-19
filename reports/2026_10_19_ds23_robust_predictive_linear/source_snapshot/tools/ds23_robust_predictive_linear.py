"""Robust conditional prediction, with zero feedback to curved calibration.

The predictive latent variables integrate uncertainty, not a receiver correction
to apply to the data. Their posterior means never replace curved calibration.
"""

import numpy as np
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from dsx01_hierarchical_bound import hierarchical_bound


def predictive_bound(raw,design,curved_gram,sigma,groups,*,student_bias=False,bias_sigma=300.):
    y,u=np.asarray(raw,float),np.asarray(design,float)
    gram=np.asarray(curved_gram,float);g=np.asarray(groups)
    if (u.ndim!=2 or y.ndim!=1 or len(y)!=len(u) or gram.shape!=(u.shape[1],u.shape[1])
            or g.shape!=y.shape or not np.issubdtype(g.dtype,np.integer) or np.any(g<0)
            or not np.isfinite(bias_sigma) or bias_sigma<0):
        raise ValueError('matching predictive data, curved precision, groups and finite nonnegative bias SD required')
    root=np.linalg.cholesky(gram)
    uncertainty=np.linalg.solve(root,u.T).T
    labels,inverse=np.unique(g,return_inverse=True)
    biases=np.zeros((len(y),len(labels)));biases[np.arange(len(y)),inverse]=bias_sigma
    features=np.column_stack((uncertainty,biases))
    prior=np.full(features.shape[1],-1,int)
    if student_bias:prior[-len(labels):]=np.arange(len(labels))
    result=hierarchical_bound(y,features,np.asarray(sigma,float),inverse,
        prior_groups=prior,noise_nu=4.,prior_nu=4.)
    result['predictive_bias_coefficient']=result['coefficient'][-len(labels):].copy()
    result['predictive_bias_prior_precision']=result['coefficient_prior_precision'][-len(labels):].copy()
    return result


def attach_robust_linear(p,entries,powers,*,student_bias=False):
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    curved_calculate=p.calculate
    def calculate(position):
        c=curved_calculate(position)
        g=p.noise_groups[p.keep]
        w=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u=c['features'][p.keep]
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        geometry=geometry_features(view,position,0.)
        mean=view.q*geometry['intercept']+geometry['features']@c['coefficient']
        prediction=predictive_bound(values-mean,geometry['features'],gram,sigma,groups,student_bias=student_bias)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo']
        c['linear_predictive_objective']=prediction['negative_twice_elbo']
        c['negative_twice_elbo']+=prediction['negative_twice_elbo']
        c['normalization_constant']+=prediction['normalization_constant']
        c['residual']=np.r_[c['residual'],prediction['residual']]
        c['linear_raw_prediction_residual_hz']=values-mean
        c['linear_elevation']=geometry['elevation']
        c['linear_noise_precision']=prediction['noise_precision']
        c['linear_bias_prior_precision']=prediction['predictive_bias_prior_precision']
        c['linear_predictive_bias_mean_hz']=300.*prediction['predictive_bias_coefficient']
        c['linear_precision_iterations']=prediction['precision_iterations']
        c['linear_final_precision_change']=prediction['final_log_precision_change']
        return c
    p.calculate=calculate;p.linear_entries=entries;p.linear_slices=slices
    p.curved_calculate=curved_calculate
    return p
