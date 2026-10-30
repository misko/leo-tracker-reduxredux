"""Conditional satellite/fragment update with receiver means held fixed.

Experimental plug-in prediction: excluded posterior coordinates are conditioned
at their means, not marginalized. This changes predictive uncertainty and score;
it is not merely a different display of the original marginal posterior.
"""
import numpy as np
from ds23_predictive_linear import linear_geometry,predictive_residual
from ds23_height_problem import geometry_features


def family_coordinates(p,families,*,include_bias=True):
    families=sorted(set(families));begin=p.hardware.shape[1]+p.smooth.shape[1]
    if not families or not set(families)<=set(p.labels):raise ValueError('existing nonempty satellite families required')
    indices=[]
    for j in families:
        indices.append(begin+p.labels.index(j))
        if j in p.supported:
            start=begin+len(p.labels)+3*p.supported.index(j);indices.extend(range(start,start+3))
    if include_bias:
        start=begin+len(p.labels)+3*len(p.supported)
        indices.extend(start+k for k,row in enumerate(p.rows) if row['candidate_index'] in families)
    return indices


def conditional_update(mean,gram,design,raw,sigma,groups,indices):
    """Use the existing low-dimensional Gaussian elimination for long scans."""
    precision=gram[np.ix_(indices,indices)]
    prediction=predictive_residual(raw,design[:,indices],precision,sigma*np.sqrt(2),groups)
    latent=prediction['coefficient'][:len(indices)]
    delta=np.zeros(len(mean));delta[indices]=np.linalg.solve(np.linalg.cholesky(precision).T,latent)
    return delta,prediction,float(np.linalg.norm(latent))


def attach_conditional_satellite_refresh(p,entries,powers,families):
    if not entries:return p
    if p.events:raise ValueError('conditional satellite experiment requires original no-event model')
    indices=family_coordinates(p,families);begin=p.hardware.shape[1]+p.smooth.shape[1]
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    curved=p.curved_calculate
    def calculate(x):
        base=curved(x);c=dict(base);geometry=geometry_features(view,x,0.);h=geometry['features']
        g=p.noise_groups[p.keep];w=np.asarray(powers)[g]*base['noise_precision'][g]/p.point_noise[p.keep]**2
        u=base['features'][p.keep];gram=np.diag(base['coefficient_prior_precision'])+u.T@(u*w[:,None])
        raw=values-view.q*geometry['intercept']-h@base['coefficient']
        delta,prediction,distance=conditional_update(base['coefficient'],gram,h,raw,sigma,groups,indices)
        c.update(coefficient=base['coefficient']+delta,latent_coefficient=base['latent_coefficient']+delta,
            conditional_residual_hz=base['conditional_residual_hz']-base['features']@delta,
            linear_raw_prediction_residual_hz=raw-h@delta,linear_elevation=geometry['elevation'],
            curved_negative_twice_elbo=base['negative_twice_elbo'],linear_predictive_objective=prediction['objective'],
            negative_twice_elbo=base['negative_twice_elbo']+prediction['objective'],
            normalization_constant=base['normalization_constant']+prediction['normalization_constant'],
            residual=np.r_[base['residual'],prediction['residual']],
            shared_satellite_receiver_change=float(np.max(abs(delta[:begin]))),
            shared_satellite_coefficient_change=delta,shared_satellite_allowed_coordinates=indices,
            conditional_satellite_shift_mahalanobis=distance,
            objective_kind='curved_ELBO_plus_predictive_density_conditioned_on_other_coefficients')
        return c
    p.calculate=calculate;p.shared_satellite_families=sorted(set(families))
    return p
